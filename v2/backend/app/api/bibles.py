"""Bibliothèque des traductions : catalogue, import, téléchargement, suppression."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

router = APIRouter()


class BibleImportRequest(BaseModel):
    """Contenu JSON d'une traduction, et le sigle sous lequel l'installer."""
    content: str = Field(..., max_length=10_000_000)  # max ~10MB JSON string
    version_id: Optional[str] = Field("", max_length=50)


@router.get("/bibles/catalogue")
async def bible_catalogue():
    """Ce qui est réellement utilisable, et ce qui ne l'est pas.

    L'état vient du moteur de lecture, pas d'une liste écrite en dur : c'est ce
    qui empêche l'interface de proposer une version que le paquet n'embarque
    pas — le pasteur demandait la Semeur et le clic ne faisait rien.
    """
    from ..main import verse_parser
    from ..services import bible_import
    chargees = list(verse_parser.bible_loader.versions.keys()) if verse_parser else []
    return bible_import.catalogue(chargees)


@router.get("/bibles/imported")
async def list_imported_bibles():
    """Traductions ajoutées par l'église, distinctes de celles livrées."""
    from ..services import bible_import
    return {"versions": bible_import.lister(), "reserved": sorted(bible_import.SIGLES_RESERVES)}


@router.post("/bibles/import")
async def import_bible(request: BibleImportRequest):
    """Installe une traduction au format du corpus VersePro.

    Le fichier reste sur le poste de l'église : VersePro ne le rediffuse pas.
    La responsabilité des droits appartient à qui l'ajoute (voir CONDITIONS.md).
    """
    import asyncio
    from ..services import bible_import
    try:
        resume = await asyncio.to_thread(bible_import.importer, request.content, request.version_id or "")
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**resume, "restart_required": True}


@router.post("/bibles/download_public/{version_id}")
async def download_public_bible(version_id: str):
    """Télécharge et installe automatiquement une Bible du domaine public."""
    import asyncio
    import urllib.request
    from ..services import bible_import
    version_id = version_id.upper().strip()
    url = bible_import.PUBLIC_DOWNLOAD_URLS.get(version_id)
    if not url:
        raise HTTPException(status_code=400, detail=f"Aucun lien de téléchargement direct pour '{version_id}'")

    def _fetch_and_install():
        req = urllib.request.Request(url, headers={"User-Agent": "VersePro/2.0"})
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
        return bible_import.importer(content, version_id)

    try:
        resume = await asyncio.to_thread(_fetch_and_install)
        return {**resume, "restart_required": True}
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Échec du téléchargement direct : {exc}")


@router.delete("/bibles/imported/{version_id}")
async def delete_imported_bible(version_id: str):
    from ..services import bible_import
    try:
        bible_import.supprimer(version_id)
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"versions": bible_import.lister(), "restart_required": True}
