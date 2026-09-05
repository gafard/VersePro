import hashlib, io, json, time, zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect
import app.main as runtime
from app.api.launch import ServiceFile
from app.core.config import settings
from app.outputs.browser import BrowserOutput
from app.services.rehearsal import new_engine, detect
from app.services.verse_parser import VerseParserService
from app.services.companion import Companion
from app.services.session_export import vers_carnet
from app.services import offline_kit, local_corrections

@pytest.fixture
def anyio_backend(): return 'asyncio'
@pytest.fixture(scope="module")
def parser(): return VerseParserService()
@pytest.fixture
def client(monkeypatch,parser,tmp_path):
    monkeypatch.setattr(runtime,'verse_parser',parser)
    monkeypatch.setattr(runtime,'semantic_service',None)
    monkeypatch.setattr(runtime,'output_manager',SimpleNamespace(outputs={'browser':BrowserOutput()}))
    monkeypatch.setattr(settings,'API_TOKEN','')
    monkeypatch.delenv('VERSEPRO_SESSION_TOKEN',raising=False)
    import app.api.launch as launch
    monkeypatch.setattr(launch,'DATA_DIR',tmp_path)
    monkeypatch.setattr(local_corrections,'DATA_DIR',tmp_path)
    return TestClient(runtime.app)

def test_portable_service_rejects_secrets_and_future_format():
    for data in [{'deepgram_api_key':'secret'},{'schema_version':2},{'format':'unknown'}]:
        with pytest.raises(ValidationError): ServiceFile(**data)

def test_service_roundtrip_and_invalid_reference_are_atomic(client):
    saved=client.post('/api/v1/services',json={'name':'Culte du test','references':['Jean 3:16','Romains 8:28']})
    assert saved.status_code==200 and len(saved.json()['references'])==2
    assert client.post('/api/v1/services',json={'references':['Jean 99:999']}).status_code==422
    assert len(client.get('/api/v1/services').json()['services'])==1

def test_private_routes_require_token(client,monkeypatch):
    monkeypatch.setenv('VERSEPRO_SESSION_TOKEN','private-test-token')
    for path in ['/api/v1/services','/api/v1/diagnostic','/api/v1/companion','/api/v1/offline-kit']:
        assert client.get(path).status_code==401
        assert client.get(path,headers={'Authorization':'Bearer private-test-token'}).status_code==200
    assert client.get('/api/v1/offline-kit/download?key=wrong').status_code==404

def test_diagnostic_excludes_secrets(client,monkeypatch):
    monkeypatch.setattr(settings,'DEEPGRAM_API_KEY','DO-NOT-EXPORT')
    text=client.get('/api/v1/diagnostic').text
    assert 'DO-NOT-EXPORT' not in text and 'model_path' not in text and 'transcript' not in text

@pytest.mark.anyio
async def test_receipt_needs_matching_scene_and_fresh_heartbeat():
    driver=BrowserOutput();ws=AsyncMock()
    await driver.send_scene({'reference':'Jn 3:16','text':'test'})
    assert driver.delivery_status()['rendered']==0
    await driver.register_connection(ws);scene=driver.current_scene['scene_id']
    driver.acknowledge(ws,{'type':'rendered','scene_id':'wrong'})
    assert driver.delivery_status()['rendered']==0
    driver.acknowledge(ws,{'type':'rendered','scene_id':scene,'surface':'obs'})
    assert driver.delivery_status()['rendered']==1
    await driver.send_scene({'reference':'Rm 8:28','text':'new'})
    driver.acknowledge(ws,{'type':'rendered','scene_id':scene})
    assert driver.delivery_status()['rendered']==0
    driver.acknowledge(ws,{'type':'rendered','scene_id':driver.current_scene['scene_id']})
    driver.receipts[ws]['rendered_at']=time.time()-30
    assert driver.delivery_status()['rendered']==0
    driver.unregister_connection(ws)
    assert driver.delivery_status()['clients']==[]

@pytest.mark.anyio
async def test_preview_cannot_ack_public_scene():
    driver=BrowserOutput();ws=AsyncMock()
    await driver.register_connection(ws,'preview');await driver.send_scene({'reference':'Jn 3:16'})
    driver.acknowledge(ws,{'type':'rendered','scene_id':driver.current_scene['scene_id']})
    assert driver.delivery_status()['rendered']==0

@pytest.mark.anyio
async def test_rehearsal_is_isolated(parser,monkeypatch):
    send=AsyncMock();monkeypatch.setattr(runtime,'broadcast_projection',send)
    original=runtime.current_projection_slide.copy();engine=new_engine(parser,None)
    result=await detect(engine,'Jean chapitre trois verset seize')
    assert result['candidate']['reference']=='Jean 3:16'
    assert engine.last_detected_ref is None and runtime.current_projection_slide==original
    send.assert_not_called()

@pytest.mark.anyio
async def test_spoken_correction_requires_review(parser):
    result=await detect(new_engine(parser,None),'Jean 3:16, pardon, Jean 14:6')
    assert result['candidate']['reference']=='Jean 14:6'
    assert result['candidate']['superseded_references']==['Jean 3:16']
    assert result['candidate']['requires_review'] and result['candidate']['detection_method']=='spoken_revision'

@pytest.mark.anyio
async def test_ordinary_pardon_keeps_reference(parser):
    result=await detect(new_engine(parser,None),'Jean 3:16 parle du pardon et de l’amour de Dieu')
    assert result['candidate']['reference']=='Jean 3:16' and result['candidate']['detection_method']!='spoken_revision'

def test_corrections_validate_and_reset(client):
    phrase='la lumière guide chacun de nos pas ce matin'
    assert client.post('/api/v1/learning/corrections',json={'text':phrase,'reference':'Jean 99:99'}).status_code==422
    assert client.post('/api/v1/learning/corrections',json={'text':phrase,'reference':'Psaume 119:105'}).status_code==200
    assert local_corrections.lookup(phrase)=='Psaumes 119:105'
    assert local_corrections.lookup('autre phrase') is None
    client.post('/api/v1/learning/reset')
    assert local_corrections.lookup(phrase) is None

def test_companion_no_private_api(client):
    c=TestClient(Companion().app)
    for path in ['/api/v1/settings','/api/v1/services','/docs','/openapi.json']:
        assert c.get(path).status_code==404
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/stream',subprotocols=['versepro','versepro.auth.invalid']): pass

def test_companion_readonly_cannot_clear(client,monkeypatch):
    companion=Companion();companion.token='test';companion.expires=time.time()+100;companion.role='viewer'
    send=AsyncMock();monkeypatch.setattr(runtime,'broadcast_projection',send)
    with TestClient(companion.app).websocket_connect('/stream',subprotocols=['versepro','versepro.auth.test']) as ws:
        assert ws.receive_json()['role']=='viewer';ws.receive_json();ws.send_json({'type':'clear'})
    send.assert_not_called()

def test_companion_rejects_cross_origin_and_expired():
    companion=Companion();companion.token='test';companion.expires=time.time()+100;c=TestClient(companion.app)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/stream',subprotocols=['versepro','versepro.auth.test'],headers={'Origin':'http://evil.example'}): pass
    companion.expires=time.time()-1
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/stream',subprotocols=['versepro','versepro.auth.test']): pass

def kit(entries):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for name,value in entries.items():z.writestr(name,value)
        z.writestr('manifest.json',json.dumps({'format':'versepro-offline','schema_version':1,'files':[{'name':k,'size':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in entries.items()]}))
    stream.seek(0);return stream

def test_kit_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):offline_kit.import_kit(kit({'../escape':b'x'}),tmp_path)
    assert list(tmp_path.iterdir())==[]

def test_kit_validates_everything_before_install(tmp_path,monkeypatch):
    names=['semantic/models/e5-base/model_quantized.onnx','semantic/models/e5-base/tokenizer.json']
    expected=hashlib.sha256(b'good').hexdigest();monkeypatch.setattr(offline_kit,'ALLOWED',{n:expected for n in names})
    with pytest.raises(ValueError):offline_kit.import_kit(kit({names[0]:b'good',names[1]:b'bad'}),tmp_path)
    assert list(tmp_path.iterdir())==[]
    assert offline_kit.import_kit(kit({n:b'good' for n in names}),tmp_path)['installed']==2
    assert offline_kit.import_kit(kit({n:b'good' for n in names}),tmp_path)['installed']==0

def test_kit_keeps_existing_models(tmp_path,monkeypatch):
    name='semantic/models/e5-base/tokenizer.json';monkeypatch.setattr(offline_kit,'ALLOWED',{name:None})
    target=tmp_path/name;target.parent.mkdir(parents=True);target.write_bytes(b'original')
    with pytest.raises(ValueError):offline_kit.import_kit(kit({name:b'new'}),tmp_path)
    assert target.read_bytes()==b'original'

def test_notebook_excludes_unprojected_and_escapes_text():
    page=vers_carnet({'name':'<script>alert(1)</script>'},[{'reference':'secret','text':'unprojected'},{'reference':'Jean 3:16','text':'<img onerror=evil>','sent_to_propresenter':1}])
    assert 'unprojected' not in page and '<script>' not in page and '<img onerror' not in page
    assert 'Jean 3:16' in page and '&lt;img' in page


def test_extracts_every_reference_in_order(client):
    response = client.post('/api/v1/bibles/extract_references', json={'text': 'Nous lirons Jean 3:16, puis Romains 8:28.\nJean 3:16 à nouveau.'})
    assert response.status_code == 200
    assert [r['reference'] for r in response.json()['references']] == ['Jean 3:16', 'Romains 8:28']


@pytest.mark.anyio
async def test_native_cancellation_waits_for_worker():
    import asyncio
    import threading
    from app.api.launch import native_operation
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    def worker():
        entered.set()
        release.wait(2)
        finished.set()
    task = asyncio.create_task(native_operation(worker))
    await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


def test_live_refuses_while_rehearsal_owns_audio(client, monkeypatch):
    import app.api.launch as launch
    monkeypatch.setattr(launch, 'audio_rehearsal_lock', SimpleNamespace(locked=lambda: True))
    with client.websocket_connect('/ws/audio') as ws:
        result = ws.receive_json()
        assert result['type'] == 'error' and 'répétition' in result['message']


def test_kit_rejects_malformed_manifest(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('manifest.json', '[]')
    stream.seek(0)
    with pytest.raises(ValueError):
        offline_kit.import_kit(stream, tmp_path)


def test_kit_cannot_follow_symlink_outside_storage(tmp_path, monkeypatch):
    outside = tmp_path / 'outside'
    outside.mkdir()
    base = tmp_path / 'data'
    base.mkdir()
    (base / 'semantic').symlink_to(outside, target_is_directory=True)
    name = 'semantic/model.bin'
    monkeypatch.setattr(offline_kit, 'ALLOWED', {name: None})
    with pytest.raises(ValueError):
        offline_kit.import_kit(kit({name: b'valid'}), base)
    assert list(outside.iterdir()) == []


@pytest.mark.anyio
async def test_all_guided_rehearsal_lines_match_expected(parser):
    from app.services.rehearsal import DEMO_LINES
    for line, reference in zip(DEMO_LINES, ['Jean 3:16', None, 'Psaumes 23:1', 'Romains 8:28']):
        result = await detect(new_engine(parser, None), line['text'])
        assert (result['candidate'] or {}).get('reference') == reference
        if reference:
            assert result['candidate']['text']


def test_correction_import_is_atomic_and_exportable(client):
    rows = {'format': 'versepro-corrections', 'schema_version': 1, 'corrections': [
        {'text': 'la lumière éclaire notre route aujourd’hui', 'reference': 'Psaumes 119:105'},
        {'text': 'une autre phrase assez longue', 'reference': 'Jean 99:99'}]}
    assert client.post('/api/v1/learning/import', json=rows).status_code == 422
    assert not local_corrections.read()
    rows['corrections'].pop()
    assert client.post('/api/v1/learning/import', json=rows).json()['count'] == 1
    exported = client.get('/api/v1/learning/corrections').json()
    assert exported['format'] == 'versepro-corrections'
    assert exported['corrections'][0]['reference'] == 'Psaumes 119:105'


def test_screen_test_does_not_erase_new_projection(client, monkeypatch):
    import app.api.launch as launch
    monkeypatch.setattr(launch, 'screen_test', None)
    started = client.post('/api/v1/projection/test', json={})
    assert started.status_code == 200
    assert client.post('/api/v1/projection/test', json={}).status_code == 409
    driver = runtime.output_manager.outputs['browser']
    driver.current_scene = {'scene_id': 'new-operator-action', 'reference': 'Jean 3:16'}
    result = client.post('/api/v1/projection/test/finish', json=started.json())
    assert result.json()['restored'] is False
    assert driver.current_scene['reference'] == 'Jean 3:16'


def test_screen_test_restores_previous_scene(client, monkeypatch):
    import app.api.launch as launch
    monkeypatch.setattr(launch, 'screen_test', None)
    driver = runtime.output_manager.outputs['browser']
    previous = driver.current_scene['text']
    started = client.post('/api/v1/projection/test', json={})
    assert client.post('/api/v1/projection/test/finish', json=started.json()).json()['restored']
    assert driver.current_scene['text'] == previous


def test_discovery_cannot_replace_a_current_passage(client):
    driver = runtime.output_manager.outputs['browser']
    driver.current_scene['reference'] = 'Romains 8:28'
    assert client.post('/api/v1/discovery/project', json={}).status_code == 409
    assert driver.current_scene['reference'] == 'Romains 8:28'


def test_discovery_projects_real_local_verse(client, monkeypatch):
    from app.outputs.manager import OutputManager
    manager = OutputManager()
    manager.outputs['browser'] = BrowserOutput()
    monkeypatch.setattr(runtime, 'output_manager', manager)
    monkeypatch.setattr(runtime, 'current_projection_slide', dict(runtime.current_projection_slide))
    response = client.post('/api/v1/discovery/project', json={})
    assert response.status_code == 200
    assert response.json()['success'] is True
    assert manager.outputs['browser'].current_scene['reference'] == 'Jean 3:16'
    assert 'Car Dieu' in manager.outputs['browser'].current_scene['text']
