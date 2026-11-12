import json
from datetime import datetime, timezone
from studyhub.extensions import db
from studyhub.models.content import Subject, SubjectTitle, PdfMaterial, PdfVersion
from studyhub.models.metadata import Category, Tag
from studyhub.models.user import User

class BackupService:
    """Administrative backup utilities and metadata export."""

    @classmethod
    def export_metadata_json(cls) -> str:
        """Serializes global library metadata into JSON."""
        subjects = db.session.query(Subject).filter(Subject.deleted_at.is_(None)).all()
        categories = db.session.query(Category).all()
        tags = db.session.query(Tag).all()

        data = {
            "platform": "StudyHub V2",
            "version": "2.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_records": len(subjects) + len(categories) + len(tags),
            "categories": [{"id": c.id, "name": c.name, "description": c.description} for c in categories],
            "tags": [{"id": t.id, "name": t.name} for t in tags],
            "subjects": []
        }

        for s in subjects:
            s_dict = {
                "id": s.id,
                "name": s.subject_name,
                "description": s.description,
                "icon": s.icon,
                "is_published": s.is_published,
                "categories": [c.name for c in s.categories],
                "tags": [t.name for t in s.tags],
                "titles": []
            }
            for t in s.titles:
                if t.deleted_at is None:
                    t_dict = {
                        "id": t.id,
                        "title_name": t.title_name,
                        "description": t.description,
                        "is_published": t.is_published,
                        "pdfs": []
                    }
                    for p in t.pdf_materials:
                        if p.deleted_at is None:
                            t_dict["pdfs"].append({
                                "id": p.id,
                                "title": p.title,
                                "storage_key": p.storage_key,
                                "original_filename": p.original_filename,
                                "file_size": p.file_size,
                                "sha256": p.sha256,
                                "download_count": p.download_count,
                                "view_count": p.view_count,
                                "uploaded_at": p.created_at.isoformat()
                            })
                    s_dict["titles"].append(t_dict)
            data["subjects"].append(s_dict)

        return json.dumps(data, indent=2)

    @classmethod
    def get_storage_inventory(cls) -> list[dict]:
        """Returns inventory of active PDF files stored in Cloudflare R2."""
        materials = db.session.query(PdfMaterial).filter(PdfMaterial.deleted_at.is_(None)).all()
        inventory = []
        for m in materials:
            inventory.append({
                "id": m.id,
                "title": m.title,
                "storage_key": m.storage_key,
                "file_size": m.file_size,
                "sha256": m.sha256,
                "subject": m.subject.subject_name,
                "title_ref": m.title_ref.title_name,
                "uploaded_by": m.uploader.username if m.uploader else "Unknown"
            })
        return inventory
