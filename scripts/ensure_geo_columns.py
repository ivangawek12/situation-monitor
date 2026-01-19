import duckdb

con = duckdb.connect("events.duckdb")
con.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS geo_query VARCHAR")
con.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS geo_label VARCHAR")
con.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS geo_country VARCHAR")
con.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS geo_type VARCHAR")
con.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS geo_lat DOUBLE")
con.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS geo_lon DOUBLE")
con.close()

print("OK: columns ensured")
