import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services import background_store


@pytest.fixture(autouse=True)
def isolated_background_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(background_store, "BACKGROUND_DIR", tmp_path / "backgrounds")


def _image_bytes(size=(1280, 720), color=(35, 80, 120), fmt="JPEG"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format=fmt)
    return output.getvalue()


def test_import_normalise_et_liste_un_fond():
    asset = background_store.save_asset(_image_bytes(), "Sanctuaire")

    assert asset["name"] == "Sanctuaire"
    assert asset["width"] == 1280 and asset["height"] == 720
    assert asset["image_url"].endswith(f"/{asset['id']}/image")
    assert background_store.list_assets() == [asset]
    assert background_store.asset_file(asset["id"], "thumbnail")[0].is_file()


def test_data_url_est_decodee_et_limitee_au_type_image():
    raw = _image_bytes(size=(128, 128), fmt="PNG")
    payload = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

    assert background_store.decode_upload(payload) == raw
    with pytest.raises(background_store.BackgroundInvalide):
        background_store.decode_upload("data:text/plain;base64,SGVsbG8=")


def test_fichier_invalide_ne_cree_aucun_asset():
    with pytest.raises(background_store.BackgroundInvalide):
        background_store.save_asset(b"ceci n'est pas une image", "Erreur")
    assert background_store.list_assets() == []


def test_resolution_ne_sactive_quavec_un_asset_existant():
    asset = background_store.save_asset(_image_bytes(), "Fond")
    settings = SimpleNamespace(
        BACKGROUND_ENABLED=True,
        BACKGROUND_ASSET=asset["id"],
        BACKGROUND_FIT="cover",
        BACKGROUND_POSITION_X=72,
        BACKGROUND_POSITION_Y=31,
        BACKGROUND_OVERLAY_COLOR="#102030",
        BACKGROUND_OVERLAY_OPACITY=0.5,
        BACKGROUND_BLUR=4,
    )

    resolved = background_store.resolve_background(settings, include_path=True)
    assert resolved["enabled"] is True
    assert resolved["position_x"] == 72 and resolved["position_y"] == 31
    assert resolved["image_path"].is_file()

    public = background_store.resolve_background(settings)
    assert "image_path" not in public

    settings.BACKGROUND_ASSET = "0000000000000000"
    assert background_store.resolve_background(settings)["enabled"] is False


def test_options_sont_bornees_avant_affichage():
    options = background_store.sanitise_options(
        fit="script", position_x=-50, position_y=180,
        overlay_color="url(javascript:1)", overlay_opacity=2, blur=99,
    )
    assert options == {
        "fit": "cover", "position_x": 0, "position_y": 100,
        "overlay_color": "#000000", "overlay_opacity": 0.9, "blur": 20,
    }


def test_suppression_retire_les_fichiers():
    asset = background_store.save_asset(_image_bytes(), "Temporaire")
    background_store.delete_asset(asset["id"])
    assert background_store.list_assets() == []
    assert background_store.asset_file(asset["id"]) is None
