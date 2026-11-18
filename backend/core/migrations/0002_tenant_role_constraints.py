from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]
    operations = [migrations.RunSQL(
        sql='''
        ALTER TABLE core_membershiprole ADD CONSTRAINT membershiprole_member_company_fk
        FOREIGN KEY (membership_id, company_id) REFERENCES core_membership (id, company_id) ON DELETE RESTRICT;
        ALTER TABLE core_membershiprole ADD CONSTRAINT membershiprole_role_company_fk
        FOREIGN KEY (role_id, company_id) REFERENCES core_role (id, company_id) ON DELETE RESTRICT;
        ''',
        reverse_sql='''
        ALTER TABLE core_membershiprole DROP CONSTRAINT membershiprole_member_company_fk;
        ALTER TABLE core_membershiprole DROP CONSTRAINT membershiprole_role_company_fk;
        ''',
    )]
