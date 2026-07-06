#!/usr/bin/env python3
import subprocess

def psql(sql):
    r = subprocess.run(
        ["docker", "exec", "citevision-v2-postgres",
         "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    return r.stdout.strip()

# Check zones table columns
print("=== zones TABLE COLUMNS ===")
print(psql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='zones' ORDER BY ordinal_position;"))

print("\n=== ALL zones ROWS ===")
print(psql("SELECT id, name, zone_kind, camera_id FROM zones LIMIT 10;"))

print("\n=== zone_vertices COLUMNS ===")
print(psql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='zone_vertices' ORDER BY ordinal_position;"))

print("\n=== zone_vertices ROWS ===")
print(psql("SELECT zone_id, vertex_order, x_norm, y_norm, distance_to_next_m FROM zone_vertices ORDER BY zone_id, vertex_order;"))

print("\n=== Zone_distance_parcourue BEHAVIOR CONFIG ===")
row = psql("SELECT id, name, zone_kind, behavior_config::text FROM zones WHERE name='Zone_distance_parcourue';")
print(row)
