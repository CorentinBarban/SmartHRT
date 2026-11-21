"""Gestionnaire centralisé des timers : un seul timer actif par clé, annulation groupée."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimerInfo:
    """Informations sur un timer actif (callback_name sert au debugging, unsub l'annule)."""

    key: str
    scheduled_time: datetime
    callback_name: str
    unsub: CALLBACK_TYPE


class TimerManager:
    """Garantit un seul timer actif par clé : schedule() annule l'éventuel timer existant."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise le gestionnaire de timers."""
        self._hass = hass
        self._timers: dict[str, TimerInfo] = {}

    def schedule(
        self,
        key: str,
        callback: Callable[[datetime], None],
        target_time: datetime,
    ) -> None:
        """Planifie un timer, annulant tout timer existant pour cette clé.

        L'annulation automatique évite les timers concurrents sur une même clé.
        target_time doit être timezone-aware.
        """
        self.cancel(key)

        unsub = async_track_point_in_time(
            self._hass,
            callback,
            target_time,
        )

        self._timers[key] = TimerInfo(
            key=key,
            scheduled_time=target_time,
            callback_name=callback.__name__,
            unsub=unsub,
        )

        _LOGGER.debug(
            "Timer '%s' programmé pour %s (callback: %s)",
            key,
            target_time.isoformat(),
            callback.__name__,
        )

    def cancel(self, key: str) -> bool:
        """Annule un timer ; retourne False si aucun timer n'existait pour cette clé."""
        timer_info = self._timers.pop(key, None)
        if timer_info:
            timer_info.unsub()
            _LOGGER.debug("Timer '%s' annulé", key)
            return True
        return False

    def cancel_all(self) -> int:
        """Annule tous les timers (déchargement) et retourne leur nombre."""
        count = len(self._timers)
        for timer_info in self._timers.values():
            timer_info.unsub()
        self._timers.clear()
        if count > 0:
            _LOGGER.debug("Tous les timers annulés (%d)", count)
        return count

    def is_active(self, key: str) -> bool:
        """Indique si un timer est actif pour cette clé."""
        return key in self._timers

    def get_info(self, key: str) -> TimerInfo | None:
        """Retourne les informations du timer, ou None."""
        return self._timers.get(key)

    @property
    def active_timers(self) -> list[str]:
        """Clés des timers actifs."""
        return list(self._timers.keys())

    @property
    def timer_count(self) -> int:
        """Nombre de timers actifs."""
        return len(self._timers)

    def get_diagnostics(self) -> dict:
        """Retourne l'état de tous les timers actifs pour le diagnostic."""
        return {
            "active_count": self.timer_count,
            "timers": [
                {
                    "key": info.key,
                    "scheduled_time": info.scheduled_time.isoformat(),
                    "callback": info.callback_name,
                }
                for info in self._timers.values()
            ],
        }

    def __repr__(self) -> str:
        """Représentation string pour le debugging."""
        return f"TimerManager(active={self.active_timers})"
