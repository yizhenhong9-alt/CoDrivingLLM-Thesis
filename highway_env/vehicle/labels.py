"""Episode-local display labels; independent of simulation IDs and policy state."""

LABEL_VERSION = 'M25-modulo1000-unique'


def vehicle_label(vehicle):
    """Keep the legacy remainder unless occupied; reserve a stable unused label.

    One namespace is shared by all vehicle classes on a road. Reservations are
    never released during that road's lifetime. No simulator RNG is consumed.
    """
    if hasattr(vehicle, 'display_id'):
        return vehicle.display_id
    road = getattr(vehicle, 'road', None)
    if road is None:
        raise ValueError('A road is required to allocate a unique vehicle label')
    if not hasattr(road, '_vehicle_display_ids'):
        road._vehicle_display_ids = set()
    used = road._vehicle_display_ids
    candidate = id(vehicle) % 1000
    for offset in range(1000):
        label = (candidate + offset) % 1000
        if label not in used:
            used.add(label)
            vehicle.display_id = label
            return label
    raise ValueError('Vehicle display label namespace exhausted (1000 per episode)')


def copy_vehicle_label(source, target):
    """A replacement/prediction object represents the same logical vehicle."""
    target.display_id = vehicle_label(source)
