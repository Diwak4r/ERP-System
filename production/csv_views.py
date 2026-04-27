import csv
import io
from typing import Any, Sequence

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render

from .models import Item, Machine, Section, Worker

ROLE_ADMIN = "ADMIN"
MAX_CSV_SIZE_BYTES = 5 * 1024 * 1024
MAX_VISIBLE_IMPORT_ERRORS = 10
CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f"}

# Map model names to actual classes and their expected CSV headers.
MODELS_MAP: dict[str, dict[str, Any]] = {
    "item": {
        "model": Item,
        "headers": ["name", "sku", "unit", "is_active"],
    },
    "worker": {
        "model": Worker,
        "headers": ["name", "employee_code", "is_daily_wage", "is_active"],
    },
    "machine": {
        "model": Machine,
        "headers": ["section_code", "name", "machine_code", "is_active"],
    },
    "section": {
        "model": Section,
        "headers": ["name", "code", "is_active"],
    },
}

UNIQUE_FIELD_BY_MODEL = {
    "item": "sku",
    "worker": "employee_code",
    "machine": "machine_code",
    "section": "code",
}


def _is_admin(user) -> bool:
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists())


def _validate_admin_access(request):
    if _is_admin(request.user):
        return None
    return HttpResponseForbidden("Only ADMIN users can access CSV import/export.")


def _normalize_headers(fieldnames: Sequence[str] | None) -> list[str]:
    if fieldnames is None:
        return []
    return [(name or "").strip() for name in fieldnames]


def _parse_boolean(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValidationError(f"Field '{field_name}' must be a boolean (true/false, yes/no, 1/0).")


def _format_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        parts: list[str] = []
        for field, messages_list in error.message_dict.items():
            if isinstance(messages_list, list):
                joined = "; ".join(str(message) for message in messages_list)
            else:
                joined = str(messages_list)
            parts.append(f"{field}: {joined}")
        return ", ".join(parts)

    if hasattr(error, "messages"):
        return "; ".join(str(message) for message in error.messages)

    return str(error)


def _safe_cell(row: dict[str, Any], header: str) -> str:
    value = row.get(header, "")
    if value is None:
        return ""
    return str(value).strip()


def _build_instance_data(model_name: str, row: dict[str, Any], expected_headers: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header in expected_headers:
        value = _safe_cell(row, header)

        if header in {"is_active", "is_daily_wage"}:
            if not value:
                raise ValidationError(f"Field '{header}' is required.")
            data[header] = _parse_boolean(value, header)
            continue

        if header == "section_code":
            if not value:
                raise ValidationError("Field 'section_code' is required.")
            section = Section.objects.filter(code=value).first()
            if section is None:
                raise ValidationError(f"Section with code '{value}' not found.")
            data["section"] = section
            continue

        data[header] = value or None

    unique_field = UNIQUE_FIELD_BY_MODEL.get(model_name)
    if unique_field:
        unique_value = data.get(unique_field)
        if unique_value and MODELS_MAP[model_name]["model"].objects.filter(**{unique_field: unique_value}).exists():
            raise ValidationError(f"{unique_field} '{unique_value}' already exists.")

    return data


def _sanitize_for_csv_export(value: Any) -> Any:
    if isinstance(value, str) and value and value[0] in CSV_INJECTION_PREFIXES:
        return f"'{value}"
    return value


@login_required
def csv_import_export_view(request):
    access_error = _validate_admin_access(request)
    if access_error:
        return access_error

    if request.method == "POST":
        model_name = request.POST.get("model_name", "")
        csv_file = request.FILES.get("csv_file")

        if model_name not in MODELS_MAP:
            messages.error(request, "Invalid model selected.")
            return redirect("production:csv-import-export")

        if csv_file is None:
            messages.error(request, "Please upload a CSV file.")
            return redirect("production:csv-import-export")

        if not csv_file.name.lower().endswith(".csv"):
            messages.error(request, "File must be a CSV.")
            return redirect("production:csv-import-export")

        if csv_file.size > MAX_CSV_SIZE_BYTES:
            messages.error(request, "File is too large. Maximum size is 5MB.")
            return redirect("production:csv-import-export")

        model_info = MODELS_MAP[model_name]
        model_class: type[models.Model] = model_info["model"]
        expected_headers: list[str] = model_info["headers"]

        try:
            decoded = csv_file.read().decode("utf-8-sig")
            csv_reader = csv.DictReader(io.StringIO(decoded))
        except UnicodeDecodeError:
            messages.error(request, "CSV must be UTF-8 encoded.")
            return redirect("production:csv-import-export")
        except Exception as error:  # pragma: no cover - defensive fallback
            messages.error(request, f"Error reading CSV file: {error}")
            return redirect("production:csv-import-export")

        normalized_headers = _normalize_headers(csv_reader.fieldnames)
        if not normalized_headers:
            messages.error(request, "CSV file is empty or invalid.")
            return redirect("production:csv-import-export")

        missing_headers = [header for header in expected_headers if header not in normalized_headers]
        if missing_headers:
            messages.error(request, f"Missing required headers: {', '.join(missing_headers)}")
            return redirect("production:csv-import-export")

        csv_reader.fieldnames = normalized_headers

        errors: list[str] = []
        rows_processed = 0

        try:
            with transaction.atomic():
                for row_idx, raw_row in enumerate(csv_reader, start=2):
                    normalized_row = {(key or "").strip(): value for key, value in raw_row.items()}
                    try:
                        data = _build_instance_data(model_name, normalized_row, expected_headers)
                        instance = model_class(**data)
                        instance.full_clean()
                        instance.save()
                        rows_processed += 1
                    except ValidationError as error:
                        errors.append(f"Row {row_idx}: {_format_validation_error(error)}")
                    except Exception as error:  # pragma: no cover - defensive fallback
                        errors.append(f"Row {row_idx}: {error}")

                if errors:
                    raise RuntimeError("Import aborted due to row errors.")
        except RuntimeError as error:
            if str(error) == "Import aborted due to row errors.":
                for validation_error in errors[:MAX_VISIBLE_IMPORT_ERRORS]:
                    messages.error(request, validation_error)
                if len(errors) > MAX_VISIBLE_IMPORT_ERRORS:
                    remaining = len(errors) - MAX_VISIBLE_IMPORT_ERRORS
                    messages.error(request, f"...and {remaining} more errors.")
            else:  # pragma: no cover - defensive fallback
                messages.error(request, f"Unexpected error during import: {error}")
            return redirect("production:csv-import-export")

        messages.success(request, f"Successfully imported {rows_processed} {model_name}(s).")
        return redirect("production:csv-import-export")

    context = {
        "models_map": MODELS_MAP,
    }
    return render(request, "production/csv/import_export.html", context)


@login_required
def csv_export_view(request, model_name):
    access_error = _validate_admin_access(request)
    if access_error:
        return access_error

    if model_name not in MODELS_MAP:
        messages.error(request, "Invalid model selected for export.")
        return redirect("production:csv-import-export")

    model_info = MODELS_MAP[model_name]
    model_class: type[models.Model] = model_info["model"]
    headers: list[str] = model_info["headers"]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{model_name}_export.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)

    for obj in model_class.objects.all():
        row: list[Any] = []
        for header in headers:
            if header == "section_code":
                value = obj.section.code if obj.section else ""
            else:
                value = getattr(obj, header, "")
            row.append(_sanitize_for_csv_export(value))
        writer.writerow(row)

    return response


@login_required
def csv_template_view(request, model_name):
    access_error = _validate_admin_access(request)
    if access_error:
        return access_error

    if model_name not in MODELS_MAP:
        messages.error(request, "Invalid model selected for template.")
        return redirect("production:csv-import-export")

    headers: list[str] = MODELS_MAP[model_name]["headers"]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{model_name}_template.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    return response
