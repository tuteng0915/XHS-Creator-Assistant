-- Request identity differs from the immutable, versioned asset snapshot.
ALTER TABLE reader_selections ADD COLUMN request_json TEXT;
