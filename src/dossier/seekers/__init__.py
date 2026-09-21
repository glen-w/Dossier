"""Seek work-evidence hits. Do not scan or embed a full history."""

from dossier.seekers.hits import Hit, Seeker, merge_hits
from dossier.seekers.quota import apply_quotas

__all__ = ["Hit", "Seeker", "apply_quotas", "merge_hits"]
