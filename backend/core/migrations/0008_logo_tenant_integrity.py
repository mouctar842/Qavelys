from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0007_company_branding_platform')]
    operations = [
        migrations.RunSQL(
            'ALTER TABLE core_companysettings ADD CONSTRAINT company_settings_logo_same_company_fk FOREIGN KEY (logo_id, company_id) REFERENCES core_companylogo (id, company_id) DEFERRABLE INITIALLY DEFERRED',
            'ALTER TABLE core_companysettings DROP CONSTRAINT company_settings_logo_same_company_fk'),
        migrations.AddConstraint(model_name='platformauditlog', constraint=models.CheckConstraint(
            condition=(models.Q(source='session', actor__isnull=False) | models.Q(source='management', actor__isnull=True)), name='platform_audit_actor_source_valid')),
    ]
