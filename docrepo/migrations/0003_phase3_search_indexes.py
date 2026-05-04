# Generated for Phase 3 search/upload optimization.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docrepo", "0002_document_correction_reason"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["is_active", "domain", "company", "period"], name="docrepo_doc_active_scope_idx"),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["indexed_at"], name="docrepo_doc_indexed_at_idx"),
        ),
        migrations.AddIndex(
            model_name="storageobject",
            index=models.Index(fields=["object_key"], name="docrepo_storage_obj_key_idx"),
        ),
        migrations.AddIndex(
            model_name="storageobject",
            index=models.Index(fields=["bucket_name"], name="docrepo_storage_bucket_idx"),
        ),
        migrations.AddIndex(
            model_name="storageobject",
            index=models.Index(fields=["etag"], name="docrepo_storage_etag_idx"),
        ),
        migrations.AddIndex(
            model_name="storageobject",
            index=models.Index(fields=["size_bytes"], name="docrepo_storage_size_idx"),
        ),
        migrations.AddIndex(
            model_name="storageobject",
            index=models.Index(fields=["bucket_name", "etag", "size_bytes"], name="docrepo_storage_dup_idx"),
        ),
    ]
