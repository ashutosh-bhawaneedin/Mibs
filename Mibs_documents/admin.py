from django.contrib import admin

from Mibs_documents.models import Document, DocumentRequest


# Register your models here.
admin.site.register(Document)
admin.site.register(DocumentRequest)
