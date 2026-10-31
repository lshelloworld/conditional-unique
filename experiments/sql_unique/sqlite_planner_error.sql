-- SQLite 3.54.0: "internal query planner error" (Hockey.Coaches, minimised)
CREATE TABLE "x4_Hockey_Coaches" ("coachID" INTEGER, "g" INTEGER, "l" INTEGER, "lgID" INTEGER, "postg" INTEGER, "postl" INTEGER, "stint" INTEGER, "t" INTEGER, "tmID" INTEGER, "w" INTEGER, "year" INTEGER);
CREATE UNIQUE INDEX i39 ON "x4_Hockey_Coaches" ("year", "tmID", "g") WHERE ("postl" = -7336743997426260411);
CREATE UNIQUE INDEX i48 ON "x4_Hockey_Coaches" ("year", "tmID", "stint") WHERE ("postl" = -7336743997426260411) OR ("postl" = -8358141127831460906) OR ("postl" = 407211082895075940) OR ("postl" = 8493001333469288333) OR ("postl" = 6482162115759618249) OR ("postl" = 7369686128406551275) OR ("postl" = 3788188144485792696);
EXPLAIN QUERY PLAN SELECT a."year", a."tmID", a."g", a."postl", a."coachID" FROM "x4_Hockey_Coaches" a LEFT JOIN "x4_Hockey_Coaches" b ON a."year" = b."year" AND a."postl" = b."postl" AND ((b."postl" = -7336743997426260411) OR (b."postl" = 407211082895075940));
-- columns referenced: ['coachID', 'g', 'postl', 'stint', 'tmID', 'year']
