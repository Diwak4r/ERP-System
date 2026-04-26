import csv
import io
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Item, Worker, Machine, Section

# Map model names to actual classes and their expected CSV headers
MODELS_MAP = {
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

def is_admin(user):
    return user.is_authenticated and user.groups.filter(name="ADMIN").exists()

@user_passes_test(is_admin)
def csv_import_export_view(request):
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        csv_file = request.FILES.get("csv_file")

        if not model_name or model_name not in MODELS_MAP:
            messages.error(request, "Invalid model selected.")
            return redirect("production:csv-import-export")

        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return redirect("production:csv-import-export")
        
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "File must be a CSV.")
            return redirect("production:csv-import-export")

        # SECURITY: Prevent DoS from extremely large files (limit to 5MB)
        if csv_file.size > 5 * 1024 * 1024:
            messages.error(request, "File is too large. Maximum size is 5MB.")
            return redirect("production:csv-import-export")

        model_info = MODELS_MAP[model_name]
        ModelClass = model_info["model"]
        expected_headers = model_info["headers"]

        # Decode file
        try:
            file_data = csv_file.read().decode("utf-8-sig")
            csv_reader = csv.DictReader(io.StringIO(file_data))
        except Exception as e:
            messages.error(request, f"Error reading CSV file: {e}")
            return redirect("production:csv-import-export")

        if not csv_reader.fieldnames:
            messages.error(request, "CSV file is empty or invalid.")
            return redirect("production:csv-import-export")

        # Check headers
        missing_headers = [h for h in expected_headers if h not in csv_reader.fieldnames]
        if missing_headers:
            messages.error(request, f"Missing required headers: {', '.join(missing_headers)}")
            return redirect("production:csv-import-export")

        errors = []
        rows_processed = 0

        try:
            with transaction.atomic():
                for row_idx, row in enumerate(csv_reader, start=2):
                    try:
                        # Extract data and process mapping
                        data = {}
                        for header in expected_headers:
                            val = row.get(header, "").strip()
                            if header == "is_active" or header == "is_daily_wage":
                                data[header] = val.lower() in ("true", "1", "yes", "t", "y")
                            elif header == "section_code":
                                # Lookup section by code
                                section = Section.objects.filter(code=val).first()
                                if not section:
                                    raise ValidationError(f"Section with code '{val}' not found.")
                                data["section"] = section
                            else:
                                data[header] = val if val else None

                        # Check for unique constraints based on the model
                        if model_name == "item":
                            if Item.objects.filter(sku=data["sku"]).exists():
                                raise ValidationError(f"Item with SKU '{data['sku']}' already exists.")
                        elif model_name == "worker":
                            if Worker.objects.filter(employee_code=data["employee_code"]).exists():
                                raise ValidationError(f"Worker with code '{data['employee_code']}' already exists.")
                        elif model_name == "machine":
                            if Machine.objects.filter(machine_code=data["machine_code"]).exists():
                                raise ValidationError(f"Machine with code '{data['machine_code']}' already exists.")
                        elif model_name == "section":
                            if Section.objects.filter(code=data["code"]).exists():
                                raise ValidationError(f"Section with code '{data['code']}' already exists.")

                        # Create the instance
                        instance = ModelClass(**data)
                        instance.full_clean()
                        instance.save()
                        rows_processed += 1
                        
                    except ValidationError as e:
                        if hasattr(e, 'message_dict'):
                            msg = ", ".join(f"{k}: {v}" for k, v in e.message_dict.items())
                        else:
                            msg = str(e.messages[0] if hasattr(e, 'messages') else e)
                        errors.append(f"Row {row_idx}: {msg}")
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")

                if errors:
                    # Rollback transaction by raising an exception
                    raise Exception("Import aborted due to row errors.")

        except Exception as e:
            # If the exception was our deliberate rollback, handle gracefully
            if str(e) == "Import aborted due to row errors.":
                for error in errors[:10]: # show up to 10 errors
                    messages.error(request, error)
                if len(errors) > 10:
                    messages.error(request, f"...and {len(errors) - 10} more errors.")
            else:
                messages.error(request, f"Unexpected error during import: {e}")
            return redirect("production:csv-import-export")

        messages.success(request, f"Successfully imported {rows_processed} {model_name}(s).")
        return redirect("production:csv-import-export")

    context = {
        "models_map": MODELS_MAP,
    }
    return render(request, "production/csv/import_export.html", context)

@user_passes_test(is_admin)
def csv_export_view(request, model_name):
    if model_name not in MODELS_MAP:
        messages.error(request, "Invalid model selected for export.")
        return redirect("production:csv-import-export")

    model_info = MODELS_MAP[model_name]
    ModelClass = model_info["model"]
    headers = model_info["headers"]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{model_name}_export.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)

    queryset = ModelClass.objects.all()
    for obj in queryset:
        row = []
        for header in headers:
            if header == "section_code":
                val = obj.section.code if obj.section else ""
            else:
                val = getattr(obj, header, "")
            
            # SECURITY: Prevent CSV Formula Injection in Excel
            if isinstance(val, str) and val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
                val = f"'{val}"
                
            row.append(val)
        writer.writerow(row)

    return response

@user_passes_test(is_admin)
def csv_template_view(request, model_name):
    if model_name not in MODELS_MAP:
        messages.error(request, "Invalid model selected for template.")
        return redirect("production:csv-import-export")

    model_info = MODELS_MAP[model_name]
    headers = model_info["headers"]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{model_name}_template.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)
    return response
