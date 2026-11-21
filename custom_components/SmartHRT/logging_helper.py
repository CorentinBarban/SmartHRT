"""Utilitaires de log permettant d'identifier l'instance SmartHRT émettrice."""

from homeassistant.config_entries import ConfigEntry


def get_log_prefix(entry: ConfigEntry, name: str | None = None) -> str:
    """Retourne un préfixe de log "[Nom#EntryID]" (entry_id tronqué à 8 caractères)."""
    display_name = name or entry.title or "SmartHRT"
    entry_id_short = entry.entry_id[:8]
    return f"[{display_name}#{entry_id_short}]"
