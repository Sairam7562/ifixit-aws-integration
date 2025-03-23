BEGIN TRANSACTION;
SELECT 'SET client_min_messages TO WARNING;' as command;
\copy (SELECT * FROM guides) TO 'backups/20250318/guides.csv' WITH CSV HEADER;
\copy (SELECT * FROM steps) TO 'backups/20250318/steps.csv' WITH CSV HEADER;
\copy (SELECT * FROM media) TO 'backups/20250318/media.csv' WITH CSV HEADER;
\copy (SELECT * FROM tags) TO 'backups/20250318/tags.csv' WITH CSV HEADER;
\copy (SELECT * FROM guide_tags) TO 'backups/20250318/guide_tags.csv' WITH CSV HEADER;
\copy (SELECT * FROM sources) TO 'backups/20250318/sources.csv' WITH CSV HEADER;
COMMIT;
