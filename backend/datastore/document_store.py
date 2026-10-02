"""Compatibility import; all office consumers share the same store and lock."""
from office_store import OfficeStore as DocumentStore
from office_store import digest, identifier, sync_directory
