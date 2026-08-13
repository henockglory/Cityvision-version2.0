import catalog from '../../../shared/frigate-track-labels.json';

export const FRIGATE_DEFAULT_VEHICLES = catalog.default_vehicles as readonly string[];
export const FRIGATE_OBJECT_SURVEILLANCE = catalog.object_surveillance as readonly string[];
/** Labels selectable in ZoneEditor for track_objects / class_filter. */
export const FRIGATE_TRACK_LABELS = catalog.ui_selectable as readonly string[];
