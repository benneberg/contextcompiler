import time
import threading
from pathlib import Path


def watch_mode(root: Path, config: dict, generator_factory):
    """
    Watch for file changes and auto-update.

    Parameters:
        root: project root
        config: runtime config
        generator_factory: callable(root, config, quick_mode=True) -> generator instance
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("Watch mode requires: pip install watchdog")
        raise SystemExit(1)

    # Delayed import to avoid circular dependency
    from .utils.files import should_skip_path

    class UpdateHandler(FileSystemEventHandler):
        def __init__(self):
            self.last_update = time.time()
            self.pending = set()
            self.timer = None

        def on_any_event(self, event):
            if event.is_directory:
                return

            path = Path(event.src_path)

            if ".llm-context" in path.parts:
                return
            if should_skip_path(path):
                return

            source_exts = {".py", ".ts", ".js", ".rs", ".go", ".cs", ".rb", ".java"}
            if path.suffix not in source_exts:
                return

            if not path.exists():
                return

            self.pending.add(path)

            if self.timer:
                self.timer.cancel()

            self.timer = threading.Timer(2.0, self.process_changes)
            self.timer.start()

        def process_changes(self):
            if not self.pending:
                return

            changes = self.pending.copy()
            self.pending.clear()

            print("")
            print("-" * 60)
            print(f"  Detected {len(changes)} file change(s)")

            for p in sorted(list(changes)[:10]):
                try:
                    rel_path = p.relative_to(root)
                    print(f"    - {rel_path}")
                except ValueError:
                    print(f"    - {p.name}")

            if len(changes) > 10:
                print(f"    ... and {len(changes) - 10} more")

            print("-" * 60)
            print("")

            try:
                generator = generator_factory(root=root, config=config, quick_mode=True, force=False)
                generator.generate()
            except Exception as e:
                print(f"  Error during update: {e}")

            self.last_update = time.time()

    handler = UpdateHandler()
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()

    print(f"Watching {root} for changes...")
    print("Press Ctrl+C to stop")
    print("")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("")
        print("Stopping watch mode...")
        if handler.timer:
            handler.timer.cancel()
        observer.stop()

    observer.join()
