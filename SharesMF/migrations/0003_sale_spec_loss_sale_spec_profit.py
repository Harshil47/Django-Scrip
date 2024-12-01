# Generated by Django 4.2.16 on 2024-11-20 21:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SharesMF', '0002_taxrate'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='spec_loss',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='sale',
            name='spec_profit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]