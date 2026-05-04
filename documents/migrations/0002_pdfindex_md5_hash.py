from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pdfindex',
            name='md5_hash',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
