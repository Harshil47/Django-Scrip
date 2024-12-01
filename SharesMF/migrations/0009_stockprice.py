# Generated by Django 4.2.16 on 2024-11-28 19:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SharesMF', '0008_usertable_family'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('script_name', models.CharField(max_length=50, unique=True)),
                ('price', models.FloatField()),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('timeslot', models.TimeField()),
            ],
        ),
    ]
