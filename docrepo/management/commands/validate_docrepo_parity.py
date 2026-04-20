from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from documents.models import PDFIndex
from docrepo.domain_inference import infer_domain_code
from docrepo.models import Document


class Command(BaseCommand):
    help = "Validate parity between legacy pdf_index and docrepo v2 by domain/company/period"

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            choices=["ALL", "CONSTANCIA_ABONO", "SEGUROS", "TREGISTRO"],
            default="ALL",
            help="Limit parity check to one domain",
        )
        parser.add_argument(
            "--sample-size",
            type=int,
            default=20,
            help="How many mismatch rows to print",
        )
        parser.add_argument(
            "--legacy-indexed-only",
            action="store_true",
            help="Count only legacy rows with is_indexed=True",
        )
        parser.add_argument(
            "--fail-on-delta",
            action="store_true",
            help="Exit with non-zero status when parity deltas are found",
        )

    def handle(self, *args, **options):
        domain_filter = None if options["domain"] == "ALL" else options["domain"]
        sample_size = max(1, int(options["sample_size"]))

        legacy_domain_counts, legacy_scope_counts, legacy_total = self._legacy_counters(
            domain_filter=domain_filter,
            indexed_only=bool(options["legacy_indexed_only"]),
        )
        v2_domain_counts, v2_scope_counts, v2_total = self._v2_counters(domain_filter=domain_filter)

        self.stdout.write(self.style.NOTICE("=== PARITY SUMMARY ==="))
        self.stdout.write(f"Legacy total: {legacy_total}")
        self.stdout.write(f"V2 total: {v2_total}")
        self.stdout.write(f"Global delta (v2 - legacy): {v2_total - legacy_total}")

        self.stdout.write(self.style.NOTICE("\n=== DOMAIN COUNTS ==="))
        all_domains = sorted(set(legacy_domain_counts.keys()) | set(v2_domain_counts.keys()))
        for domain in all_domains:
            legacy_count = legacy_domain_counts.get(domain, 0)
            v2_count = v2_domain_counts.get(domain, 0)
            delta = v2_count - legacy_count
            self.stdout.write(
                f"{domain:18s} legacy={legacy_count:6d} v2={v2_count:6d} delta={delta:6d}"
            )

        mismatches = self._build_scope_mismatches(legacy_scope_counts, v2_scope_counts)

        self.stdout.write(self.style.NOTICE("\n=== SCOPE MISMATCHES (domain, company, year, month) ==="))
        self.stdout.write(f"Total mismatches: {len(mismatches)}")
        if mismatches:
            for item in mismatches[:sample_size]:
                self.stdout.write(
                    "domain={domain} company={company} year={year} month={month} "
                    "legacy={legacy} v2={v2} delta={delta}".format(**item)
                )

        if options["fail_on_delta"] and (legacy_total != v2_total or mismatches):
            raise CommandError("Parity validation failed: deltas detected.")

        self.stdout.write(self.style.SUCCESS("Parity validation finished."))

    def _legacy_counters(self, domain_filter=None, indexed_only=False):
        domain_counts: Counter[str] = Counter()
        scope_counts: Counter[tuple[str, str, int | None, int | None]] = Counter()
        total = 0

        queryset = PDFIndex.objects.all().only(
            "razon_social",
            "año",
            "mes",
            "minio_object_name",
            "tipo_documento",
            "is_indexed",
        )
        if indexed_only:
            queryset = queryset.filter(is_indexed=True)

        for row in queryset.iterator(chunk_size=1000):
            domain_code = infer_domain_code(row.minio_object_name, row.tipo_documento)
            if domain_filter and domain_code != domain_filter:
                continue

            company = self._normalize_text(row.razon_social)
            year = self._safe_int(row.año)
            month = self._safe_int(row.mes)

            total += 1
            domain_counts[domain_code] += 1
            scope_counts[(domain_code, company, year, month)] += 1

        return domain_counts, scope_counts, total

    def _v2_counters(self, domain_filter=None):
        domain_counts: Counter[str] = Counter()
        scope_counts: Counter[tuple[str, str, int | None, int | None]] = Counter()
        total = 0

        queryset = Document.objects.select_related("domain", "company", "period").filter(is_active=True)
        if domain_filter:
            queryset = queryset.filter(domain__code=domain_filter)

        for doc in queryset.iterator(chunk_size=1000):
            domain_code = doc.domain.code
            company = self._normalize_text(doc.company.name)
            year = doc.period.year if doc.period else None
            month = doc.period.month if doc.period else None

            total += 1
            domain_counts[domain_code] += 1
            scope_counts[(domain_code, company, year, month)] += 1

        return domain_counts, scope_counts, total

    def _build_scope_mismatches(self, legacy_scope_counts, v2_scope_counts):
        mismatches = []
        all_keys = set(legacy_scope_counts.keys()) | set(v2_scope_counts.keys())

        for key in all_keys:
            legacy_count = legacy_scope_counts.get(key, 0)
            v2_count = v2_scope_counts.get(key, 0)
            if legacy_count == v2_count:
                continue

            domain, company, year, month = key
            mismatches.append(
                {
                    "domain": domain,
                    "company": company,
                    "year": year,
                    "month": month,
                    "legacy": legacy_count,
                    "v2": v2_count,
                    "delta": v2_count - legacy_count,
                    "sort_key": abs(v2_count - legacy_count),
                }
            )

        mismatches.sort(key=lambda item: item["sort_key"], reverse=True)
        for item in mismatches:
            item.pop("sort_key", None)
        return mismatches

    def _normalize_text(self, value):
        return (value or "DESCONOCIDO").strip().upper()

    def _safe_int(self, value):
        try:
            parsed = int(str(value).strip())
            return parsed
        except (TypeError, ValueError):
            return None
