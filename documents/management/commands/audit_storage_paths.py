import re
from django.core.management.base import BaseCommand
from django.conf import settings
from docrepo.models import StorageObject
from documents.utils import minio_client
from minio.commonconfig import CopySource

class Command(BaseCommand):
    help = 'Audit and potentially rename storage paths in MinIO to ensure "Planillas " prefix for year-based paths'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=True,
            help='Only report paths and simulated changes without applying them (Default)',
        )
        parser.add_argument(
            '--execute',
            action='store_false',
            dest='dry_run',
            help='Actually perform the renames in MinIO and database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        bucket = settings.MINIO_BUCKET

        self.stdout.write(self.style.SUCCESS(f"Starting storage path audit (Dry-run: {dry_run})"))

        # Regex patterns
        pattern_planillas = re.compile(r'^Planillas\s+20\d{2}/')
        pattern_year_only = re.compile(r'^20\d{2}/')

        counts = {
            'matches_planillas': 0,
            'matches_year_only': 0,
            'other': 0,
        }

        objects_to_rename = []

        storage_objects = StorageObject.objects.all()
        total = storage_objects.count()
        
        if total == 0:
            self.stdout.write("No StorageObjects found in database.")
            return

        for obj in storage_objects:
            key = obj.object_key
            if pattern_planillas.match(key):
                counts['matches_planillas'] += 1
            elif pattern_year_only.match(key):
                counts['matches_year_only'] += 1
                objects_to_rename.append(obj)
            else:
                counts['other'] += 1

        # Summary Report
        self.stdout.write("\n--- Summary Report ---")
        self.stdout.write(f"Total objects analyzed: {total}")
        self.stdout.write(f"Already prefixed 'Planillas 20XX/': {counts['matches_planillas']}")
        self.stdout.write(self.style.WARNING(f"Require 'Planillas ' prefix (20XX/...): {counts['matches_year_only']}"))
        self.stdout.write(f"Other patterns: {counts['other']}")
        self.stdout.write("----------------------\n")

        if not objects_to_rename:
            self.stdout.write(self.style.SUCCESS("No paths requiring updates were found."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run enabled. No changes will be made."))
            for obj in objects_to_rename:
                new_key = f"Planillas {obj.object_key}"
                self.stdout.write(f"Simulated: {obj.object_key} -> {new_key}")
            self.stdout.write(f"\nTotal simulated renames: {len(objects_to_rename)}")
            self.stdout.write(self.style.SUCCESS("\nRun with --execute to apply changes."))
        else:
            self.stdout.write(self.style.WARNING(f"Executing renames for {len(objects_to_rename)} objects..."))
            success_count = 0
            error_count = 0

            for obj in objects_to_rename:
                old_key = obj.object_key
                new_key = f"Planillas {old_key}"
                
                # Verify source object exists before attempting rename
                try:
                    minio_client.stat_object(bucket, old_key)
                except Exception as stat_err:
                    self.stdout.write(self.style.WARNING(f"Source object not found, skipping: {old_key}"))
                    continue
                # Perform rename (copy + delete + DB update)
                try:
                    # 1. Copy object in MinIO
                    copy_source = CopySource(bucket, old_key)
                    minio_client.copy_object(bucket, new_key, copy_source)
                    
                    # 2. Delete old object in MinIO
                    minio_client.remove_object(bucket, old_key)
                    
                    # 3. Update Database
                    obj.object_key = new_key
                    obj.save()
                    
                    success_count += 1
                    self.stdout.write(f"Renamed: {old_key} -> {new_key}")
                except Exception as e:
                    error_count += 1
                    self.stdout.write(self.style.ERROR(f"Failed to rename {old_key}: {str(e)}"))

            self.stdout.write(f"\nTask completed. Successes: {success_count}, Errors: {error_count}")
