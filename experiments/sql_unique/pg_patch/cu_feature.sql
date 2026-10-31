-- Feature tests for enable_conditional_unique (PostgreSQL 18.6 + condunique patch).
-- Each case: plan with the setting off and on, and the results of both plans compared.
\pset pager off
set client_min_messages = warning;
drop schema if exists cu cascade;
create schema cu;
set search_path = cu;

create function cu_check(q text) returns text language plpgsql as $$
declare d bigint;
begin
  perform set_config('enable_conditional_unique', 'off', true);
  execute 'create temp table _off as ' || q;
  perform set_config('enable_conditional_unique', 'on', true);
  execute 'create temp table _on as ' || q;
  execute 'select count(*) from ((table _off except all table _on) union all (table _on except all table _off)) x' into d;
  drop table _off; drop table _on;
  return case when d = 0 then 'same result' else 'DIFFERENT: ' || d end;
end $$;

-- (1) soft delete: e-mail unique among live users; duplicates and nulls among deleted ones
create table users (id int primary key, email text not null, name text, deleted_at timestamptz);
create unique index users_email_live on users (email) where deleted_at is null;
insert into users select i, 'u' || (i % 700), 'n' || i, case when i > 700 then now() end
  from generate_series(1, 1000) i;
create table orders (id int primary key, email text, amount int);
insert into orders select i, 'u' || (i % 900), i % 50 from generate_series(1, 5000) i;
analyze users, orders;

\echo '(1a) left join on a live-user scope: removable'
set enable_conditional_unique = off;
explain (costs off) select o.* from orders o left join users u on u.email = o.email and u.deleted_at is null;
set enable_conditional_unique = on;
explain (costs off) select o.* from orders o left join users u on u.email = o.email and u.deleted_at is null;
select cu_check('select o.* from orders o left join users u on u.email = o.email and u.deleted_at is null');

\echo '(1b) without the scope: not removable (deleted users repeat e-mails)'
explain (costs off) select o.* from orders o left join users u on u.email = o.email;
select cu_check('select o.* from orders o left join users u on u.email = o.email');

\echo '(1c) semi-join to inner join'
set enable_conditional_unique = off;
explain (costs off) select * from orders o where o.email in (select email from users where deleted_at is null);
set enable_conditional_unique = on;
explain (costs off) select * from orders o where o.email in (select email from users where deleted_at is null);
select cu_check('select * from orders o where o.email in (select email from users where deleted_at is null)');

\echo '(1d) GROUP BY email, name, id over live users: id and name are redundant'
set enable_conditional_unique = off;
explain (costs off) select u.email, u.name, count(*) from users u join orders o on o.email = u.email
  where u.deleted_at is null group by u.email, u.name;
set enable_conditional_unique = on;
explain (costs off) select u.email, u.name, count(*) from users u join orders o on o.email = u.email
  where u.deleted_at is null group by u.email, u.name;
select cu_check('select u.email, u.name, count(*) from users u join orders o on o.email = u.email where u.deleted_at is null group by u.email, u.name');

-- (2) per-status uniqueness: the union of two scopes is not a scope of a key
create table codes (id int primary key, code int, status text);
create unique index codes_a on codes (code) where status = 'a';
create unique index codes_b on codes (code) where status = 'b';
insert into codes select i, i / 3, case i % 3 when 0 then 'a' when 1 then 'b' else 'c' end
  from generate_series(1, 900) i;   -- every code once per status
analyze codes;
\echo '(2a) status = a: removable'
explain (costs off) select o.* from orders o left join codes c on c.code = o.amount and c.status = 'a';
select cu_check('select o.* from orders o left join codes c on c.code = o.amount and c.status = ''a''');
\echo '(2b) status in (a, b): not removable'
explain (costs off) select o.* from orders o left join codes c on c.code = o.amount and c.status in ('a', 'b');
select cu_check('select o.* from orders o left join codes c on c.code = o.amount and c.status in (''a'', ''b'')');
\echo '(2c) status <> c: not removable (a and b rows share codes)'
explain (costs off) select o.* from orders o left join codes c on c.code = o.amount and c.status <> 'c';

-- (3) tenant-scoped names: (tenant, name) unique among active rows; tenant fixed by the query
create table items (id int primary key, tenant int not null, name text, active bool not null);
create unique index items_tn on items (tenant, name) where active;
insert into items select i, i % 10, 'x' || (i % 100), i % 1000 < 500 from generate_series(1, 2000) i
  on conflict (tenant, name) where active do nothing;   -- inactive rows repeat names
analyze items;
create table refs (id int primary key, name text);
insert into refs select i, 'x' || (i % 120) from generate_series(1, 3000) i;
analyze refs;
\echo '(3) tenant = 3 and active, join on name: removable'
set enable_conditional_unique = off;
explain (costs off) select r.* from refs r left join items i on i.name = r.name and i.tenant = 3 and i.active;
set enable_conditional_unique = on;
explain (costs off) select r.* from refs r left join items i on i.name = r.name and i.tenant = 3 and i.active;
select cu_check('select r.* from refs r left join items i on i.name = r.name and i.tenant = 3 and i.active');
\echo '(3b) active only: not removable on name alone'
explain (costs off) select r.* from refs r left join items i on i.name = r.name and i.active;

-- (4) nulls not distinct: GROUP BY k, v under the scope collapses to k, nulls included
create table nnd (id int primary key, k int, v int, flag bool);
create unique index nnd_k on nnd (k) nulls not distinct where flag;
insert into nnd values (1, null, 10, true), (2, 1, 20, true), (3, 1, 30, false), (4, null, 40, false), (5, 2, 50, true);
analyze nnd;
\echo '(4a) GROUP BY k, v where flag: v is redundant'
set enable_conditional_unique = off;
explain (costs off) select k, v, count(*) from nnd where flag group by k, v;
set enable_conditional_unique = on;
explain (costs off) select k, v, count(*) from nnd where flag group by k, v;
select cu_check('select k, v, count(*) from nnd where flag group by k, v');
\echo '(4b) the same with a nulls-distinct index: not reducible (two null k rows may differ on v)'
create table nd (id int primary key, k int, v int, flag bool);
create unique index nd_k on nd (k) where flag;
insert into nd values (1, null, 10, true), (2, null, 20, true), (3, 1, 30, true);
analyze nd;
explain (costs off) select k, v, count(*) from nd where flag group by k, v;
select cu_check('select k, v, count(*) from nd where flag group by k, v');
\echo '(4c) ... but with k is not null in the query it is'
explain (costs off) select k, v, count(*) from nd where flag and k is not null group by k, v;
select cu_check('select k, v, count(*) from nd where flag and k is not null group by k, v');

-- (5) the shape of bug #17975: the predicate holds only through a join clause
create table t1 (a int, c int);
create table t2 (a int, b int);
create unique index t2_a_b1 on t2 (a) where b = 1;
insert into t1 select i % 20, i % 3 from generate_series(1, 200) i;
insert into t2 select i % 20, 1 from generate_series(1, 20) i;
insert into t2 select i % 20, 2 from generate_series(1, 60) i;
analyze t1, t2;
\echo '(5a) on t2.b = t1.c: the scope of t2 is not fixed, must not be removed'
explain (costs off) select t1.* from t1 left join t2 on t1.a = t2.a and t2.b = t1.c;
select cu_check('select t1.* from t1 left join t2 on t1.a = t2.a and t2.b = t1.c');
\echo '(5b) with where t1.c = 1 the planner derives t2.b = 1 for the scan of t2: removable'
explain (costs off) select t1.* from t1 left join t2 on t1.a = t2.a and t2.b = t1.c where t1.c = 1;
select cu_check('select t1.* from t1 left join t2 on t1.a = t2.a and t2.b = t1.c where t1.c = 1');
\echo '(5c) inner join on a non-null-scoped index (join.sql test): inner unique is sound here'
create table j1 (id1 int, id2 int, primary key (id1, id2));
create table j2 (id1 int, id2 int, primary key (id1, id2));
create unique index j1_id2_idx on j1 (id2) where id2 is not null;
explain (verbose, costs off) select * from j1 inner join j2 on j1.id2 = j2.id2;

-- (6) translation limits: an untranslatable predicate makes an index unusable
create table ex (id int primary key, k int, s text);
create unique index ex_k on ex (k) where length(s) > 3;
explain (costs off) select o.* from orders o left join ex on ex.k = o.amount and length(ex.s) > 3;


-- (7) DISTINCT removal: rows of one relation, unique on the DISTINCT columns with nulls equal (U=)
\echo '(7a) DISTINCT over the scope of a NULLS NOT DISTINCT index: removable'
explain (costs off) select distinct k from nnd where flag;
select cu_check('select distinct k from nnd where flag');
\echo '(7b) DISTINCT over a nulls-distinct scope: not removable (two null k rows form one group)'
explain (costs off) select distinct k from nd where flag;
select cu_check('select distinct k from nd where flag');
\echo '(7c) ... but with k is not null in the query it is'
explain (costs off) select distinct k from nd where flag and k is not null;
select cu_check('select distinct k from nd where flag and k is not null');
\echo '(7d) more DISTINCT columns than the key: removable'
explain (costs off) select distinct v, k from nnd where flag;
select cu_check('select distinct v, k from nnd where flag');
\echo '(7e) outside the scope: not removable'
explain (costs off) select distinct k from nnd;
select cu_check('select distinct k from nnd');
\echo '(7f) DISTINCT ON: not touched (DISTINCT over joins: section 8)'
explain (costs off) select distinct on (k) k, v from nnd where flag order by k, v;
\echo '(7g) live e-mail addresses, NOT NULL key: removable'
explain (costs off) select distinct email from users where deleted_at is null;
select cu_check('select distinct email from users where deleted_at is null');


-- (8) DISTINCT and GROUP BY through joins: every relation determined by the DISTINCT or GROUP BY
-- columns (U= on its own columns, or U on columns equated with determined ones)
create table ue (user_id int not null, email text not null, "primary" bool not null);
create unique index ue_primary on ue (user_id, "primary") where "primary";
insert into ue select i, 'p' || i, true from generate_series(1, 900) i;
insert into ue select i, 's' || i, false from generate_series(1, 1000) i;
insert into ue select i, 't' || i, false from generate_series(1, 300) i;
analyze ue;
\echo '(8a) users with their primary address (Discourse pattern): removable'
explain (costs off) select distinct u.id, ue.email from users u join ue on ue.user_id = u.id and ue."primary";
select cu_check('select distinct u.id, ue.email from users u join ue on ue.user_id = u.id and ue."primary"');
\echo '(8b) all addresses: not removable (up to three per user; still unique on (u.id, email) only by data)'
explain (costs off) select distinct u.id, ue."primary" from users u join ue on ue.user_id = u.id;
select cu_check('select distinct u.id, ue."primary" from users u join ue on ue.user_id = u.id');
\echo '(8c) left join to the primary address: removable'
explain (costs off) select distinct u.id, ue.email from users u left join ue on ue.user_id = u.id and ue."primary";
select cu_check('select distinct u.id, ue.email from users u left join ue on ue.user_id = u.id and ue."primary"');
\echo '(8d) only the nullable side in DISTINCT: not removable (users without a primary address give null rows)'
explain (costs off) select distinct ue.email from users u left join ue on ue.user_id = u.id and ue."primary";
select cu_check('select distinct ue.email from users u left join ue on ue.user_id = u.id and ue."primary"');
\echo '(8e) GROUP BY without aggregates over the join: removed'
explain (costs off) select u.id, ue.email from users u join ue on ue.user_id = u.id and ue."primary" group by u.id, ue.email;
select cu_check('select u.id, ue.email from users u join ue on ue.user_id = u.id and ue."primary" group by u.id, ue.email');
\echo '(8f) GROUP BY with count(*): the address drops out of the key'
explain (costs off) select u.id, ue.email, count(*) from users u join ue on ue.user_id = u.id and ue."primary"
  join orders o on o.email = u.email group by u.id, ue.email;
select cu_check('select u.id, ue.email, count(*) from users u join ue on ue.user_id = u.id and ue."primary" join orders o on o.email = u.email group by u.id, ue.email');
\echo '(8g) a left join whose ON clause reads an undetermined outer table: key kept'
create table m6t (a int not null, y int not null);
create table m6o (k int not null, x int not null);
create table m6u (x int not null, y int not null, d int);
create unique index on m6o (k);
create unique index on m6u (x) where d is null;
insert into m6t values (1, 1), (1, 2); insert into m6o values (1, 10); insert into m6u values (10, 1, null);
analyze m6t, m6o, m6u;
explain (costs off) select o.k, u.y, count(*) from m6t t join m6o o on t.a = o.k
  left join m6u u on o.x = u.x and t.y <> u.y and u.d is null group by o.k, u.y;
select cu_check('select o.k, u.y, count(*) from m6t t join m6o o on t.a = o.k left join m6u u on o.x = u.x and t.y <> u.y and u.d is null group by o.k, u.y');
\echo '(8h) the inner side of a semi-join adds no rows: removable'
explain (costs off) select distinct u.email from users u where u.deleted_at is null and u.id in (select user_id from ue);
select cu_check('select distinct u.email from users u where u.deleted_at is null and u.id in (select user_id from ue)');
\echo '(8j) a semi-join fixes nothing: customers that bought, by name and state; state kept (TPC-DS q35)'
create table cu8c (id int primary key, name text not null, addr int not null);
create table cu8a (id int primary key, state text not null);
create table cu8s (cid int not null);
insert into cu8c values (1, 'ann', 1), (2, 'bob', 1); insert into cu8a values (1, 'CA'), (2, 'NY');
insert into cu8s values (1), (2), (2);
analyze cu8c, cu8a, cu8s;
explain (costs off) select a.state, c.name, count(*) from cu8c c join cu8a a on a.id = c.addr
  where c.id in (select cid from cu8s) group by a.state, c.name;
select cu_check('select a.state, c.name, count(*) from cu8c c join cu8a a on a.id = c.addr where c.id in (select cid from cu8s) group by a.state, c.name');
\echo '(8i) full join: not touched'
explain (costs off) select distinct u.id, ue.email from users u full join ue on ue.user_id = u.id and ue."primary";


-- (9) CHECK constraints narrow the scope: a row passes CHECK c if c is true or null
\echo '(9a) CHECK (status = 1) on a nullable column: rows with a null status pass it; not removable'
create table c9a (k int not null, status int, constraint c9a_s check (status = 1));
create unique index on c9a (k) where status = 1;
insert into c9a values (1, 1), (1, null), (1, null), (2, null);
analyze c9a;
explain (costs off) select distinct k from c9a;
select cu_check('select distinct k from c9a');
\echo '(9b) MusicBrainz aliases: CHECK ties a primary alias to a non-null locale; removable'
create table c9b (artist int not null, locale text, primary_for_locale bool not null default false,
  constraint primary_check check ((locale is null and primary_for_locale is false) or (locale is not null)));
create unique index on c9b (artist, locale) where primary_for_locale = true and locale is not null;
insert into c9b values (1, 'en', true), (1, 'en', false), (1, null, false), (1, null, false), (2, 'de', true);
analyze c9b;
explain (costs off) select distinct artist, locale from c9b where primary_for_locale;
select cu_check('select distinct artist, locale from c9b where primary_for_locale');
\echo '(9c) a NOT VALID CHECK may be violated by old rows: not used'
create table c9c (k int not null, s int not null);
create unique index on c9c (k) where s = 1;
insert into c9c values (1, 1), (1, 2), (1, 2);
alter table c9c add constraint c9c_s check (s = 1) not valid;
analyze c9c;
explain (costs off) select distinct k from c9c;
select cu_check('select distinct k from c9c');
\echo '(9d) a NOT ENFORCED CHECK: not used'
create table c9d (k int not null, s int not null, constraint c9d_s check (s = 1) not enforced);
create unique index on c9d (k) where s = 1;
insert into c9d values (1, 1), (1, 2), (1, 2);
analyze c9d;
explain (costs off) select distinct k from c9d;
select cu_check('select distinct k from c9d');
\echo '(9e) CHECK (flag) on a nullable boolean: null flags pass; not removable'
create table c9e (k int not null, flag bool, constraint c9e_f check (flag));
create unique index on c9e (k) where flag;
insert into c9e values (1, true), (1, null), (1, null);
analyze c9e;
explain (costs off) select distinct k from c9e;
select cu_check('select distinct k from c9e');

-- (10) unconditional keys whose columns the restriction fixes (no partial index on the table)
\echo '(10a) UNIQUE (ns, title), WHERE ns = 0: GROUP BY title, len reduces to title'
create table c10 (id int primary key, ns int not null, title text not null, len int);
create unique index on c10 (ns, title);
insert into c10 select i, i % 3, 't' || (i / 3), i % 7 from generate_series(1, 3000) i;
analyze c10;
explain (costs off) select title, len, count(*) from c10 where ns = 0 group by title, len;
select cu_check('select title, len, count(*) from c10 where ns = 0 group by title, len');
\echo '(10b) WHERE ns IN (0, 1): titles repeat across namespaces; kept'
explain (costs off) select title, len, count(*) from c10 where ns in (0, 1) group by title, len;
select cu_check('select title, len, count(*) from c10 where ns in (0, 1) group by title, len');
\echo '(10c) nullable title: UNIQUE allows several nulls, GROUP BY puts them together; kept'
create table c10c (id int primary key, ns int not null, title text, len int);
create unique index on c10c (ns, title);
insert into c10c values (1, 0, null, 1), (2, 0, null, 2), (3, 0, 'a', 1);
analyze c10c;
explain (costs off) select title, len, count(*) from c10c where ns = 0 group by title, len;
select cu_check('select title, len, count(*) from c10c where ns = 0 group by title, len');

reset enable_conditional_unique;
