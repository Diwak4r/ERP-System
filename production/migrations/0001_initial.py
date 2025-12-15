from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Section",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("code", models.CharField(max_length=50, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Worker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("employee_code", models.CharField(max_length=50, unique=True)),
                ("is_daily_wage", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Item",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("sku", models.CharField(max_length=100, unique=True)),
                ("unit", models.CharField(choices=[("KG", "Kg"), ("PCS", "Pieces"), ("OTHER", "Other")], default="PCS", max_length=10)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="TargetRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_qty", models.DecimalField(decimal_places=2, max_digits=12)),
                ("shift_hours", models.DecimalField(decimal_places=2, max_digits=5)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="production.item")),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="production.section")),
            ],
            options={"ordering": ["section__name", "item__name", "-start_date"], "unique_together": {("section", "item", "start_date", "end_date")}},
        ),
        migrations.CreateModel(
            name="ProductionEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_date", models.DateField()),
                ("target_qty", models.DecimalField(decimal_places=2, max_digits=12)),
                ("actual_qty", models.DecimalField(decimal_places=2, max_digits=12)),
                ("shift_hours", models.DecimalField(decimal_places=2, max_digits=5)),
                ("overtime_hours", models.DecimalField(decimal_places=2, default=0, max_digits=7)),
                ("target_met", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="production_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="production.item")),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="production.section")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="production.worker")),
            ],
            options={"ordering": ["-entry_date", "section__name", "worker__name"]},
        ),
        migrations.AddField(
            model_name="section",
            name="supervisors",
            field=migrations.ManyToManyField(blank=True, related_name="sections", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name="productionentry",
            index=models.Index(fields=["entry_date", "section", "item"], name="production_entry_idx"),
        ),
    ]
