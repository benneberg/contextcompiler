from datetime import datetime, timezone


def get_timestamp() -> str:
    """Get current UTC timestamp as string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable string."""
    for unit in ["B", "KB", "MB"]:
        if size_bytes < 1024:
            if unit == "B":
                return f"{size_bytes:.0f}{unit}"
            return f"{size_bytes:.1f}{unit}"
        size_bytes = size_bytes / 1024
    return f"{size_bytes:.1f}GB"
