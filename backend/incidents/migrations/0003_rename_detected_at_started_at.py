from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('incidents', '0002_alter_incident_detected_at'),
    ]

    operations = [
        migrations.RenameField(
            model_name='incident',
            old_name='detected_at',
            new_name='started_at',
        ),
    ]
