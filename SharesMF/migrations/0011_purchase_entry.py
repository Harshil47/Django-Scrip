# Generated by Django 4.2.16 on 2024-11-30 23:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SharesMF', '0010_alter_stockprice_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchase',
            name='entry',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
