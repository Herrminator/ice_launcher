 
def status() -> dict[str, dict[str, str | int]]:
    from . import updaters

    status_dict: dict[str, dict[str, str | int]] = {}
    for mount, updater in updaters.items():
        status_dict[mount] = {
            "mount": updater.mount,
            "stream": updater.stream,
            "title": updater.last,
            "error_count": updater.errcnt,
        }
    return status_dict
