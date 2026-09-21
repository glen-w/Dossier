"""Thin explicit adapter registry.

Append a Contribution here when a source is in hand. No entry points, no
plugin directory, no import of every module under sources/.
"""

from __future__ import annotations

from dataclasses import dataclass

from dossier.sources.applications import ApplicationsSource
from dossier.sources.base import Source
from dossier.sources.chatgpt import ChatGPTSource
from dossier.sources.employer import EmployerSource
from dossier.sources.git import GitSource
from dossier.sources.linkedin import LinkedInSource
from dossier.sources.mbox import MboxSource
from dossier.sources.meetings import MeetingsSource
from dossier.sources.pubs import PubsSource
from dossier.sources.slack import SlackSource
from dossier.sources.transcripts import TranscriptsSource


@dataclass
class Contribution:
    name: str
    source: Source


CONTRIBUTIONS: list[Contribution] = [
    Contribution("pubs", PubsSource()),
    Contribution("chatgpt", ChatGPTSource()),
    Contribution("linkedin", LinkedInSource()),
    Contribution("applications", ApplicationsSource()),
    Contribution("transcripts", TranscriptsSource()),
    Contribution("slack", SlackSource()),
    Contribution("mbox", MboxSource()),
    Contribution("meetings", MeetingsSource()),
    Contribution("employer", EmployerSource()),
    Contribution("git", GitSource()),
]


def contribution(name: str) -> Contribution | None:
    for item in CONTRIBUTIONS:
        if item.name == name:
            return item
    return None
