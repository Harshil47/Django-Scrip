# Generated by Django 4.2.16 on 2024-12-02 18:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SharesMF', '0012_usertable_data_entry'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchase',
            name='referenced_by',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]