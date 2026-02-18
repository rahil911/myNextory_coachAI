"""
notification_bridge.py — Bridge between Command Center and the notification router.

Imports the notification router from .claude/integrations/notifications/router.py
and provides a singleton for use in services. Falls back gracefully if not available.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger("baap.notification_bridge")

# __file__ = .claude/command-center/backend/services/notification_bridge.py (5 levels up to project root)
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent

# .claude is not a valid Python package (dot prefix), so add integrations dir to sys.path
_integrations_dir = _project_root / ".claude" / "integrations"
if str(_integrations_dir) not in sys.path:
    sys.path.insert(0, str(_integrations_dir))

_router = None


def get_notification_router():
    """Get or create the notification router singleton."""
    global _router
    if _router is not None:
        return _router

    try:
        from notifications.router import NotificationRouter
        config_path = _integrations_dir / "notifications" / "notifications.yaml"
        _router = NotificationRouter.from_config(str(config_path))
        logger.info(f"Notification router loaded from {config_path}")
    except ImportError as e:
        logger.warning(f"Could not import notification router: {e} — notifications disabled")
        _router = None
    except Exception as e:
        logger.warning(f"Failed to initialize notification router: {e} — notifications disabled")
        _router = None

    return _router
