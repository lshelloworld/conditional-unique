import json, sys
from collections import Counter

OUT = sys.argv[1]
S = []

def add(app, index, table, site, code, construct, sql, j, s, conf, more, notes):
    S.append(dict(app=app, index=index, table=table, site=site, code=code, construct=construct, sql=sql,
                  joins_on_index_key=j, scope_implies_predicate=s, confidence=conf, more=more, notes=notes))

# ---------------- forem ----------------
F = "forem"
add(F, "index_articles_on_canonical_url", "articles", "app/models/article.rb:283",
    "validates :canonical_url,\n  uniqueness: { allow_nil: true, scope: :published, message: unique_url_error },\n  if: :published?",
    "lookup",
    "SELECT 1 AS one FROM \"articles\" WHERE \"articles\".\"canonical_url\" = 'https://x.com/a' AND \"articles\".\"published\" = TRUE LIMIT 1",
    None, True, "high", 0,
    "Validation only runs when published?, so the scope value is always TRUE: matches predicate (published IS TRUE). On update AR adds AND id != 1. canonical_url is not a FK; no joins on it anywhere.")

add(F, "index_articles_on_feed_source_url", "articles", "app/models/article.rb:288",
    "validates :feed_source_url,\n  uniqueness: { allow_nil: true, scope: :published, message: unique_url_error },\n  if: :published?",
    "lookup",
    "SELECT 1 AS one FROM \"articles\" WHERE \"articles\".\"feed_source_url\" = 'https://x.com/a' AND \"articles\".\"published\" = TRUE LIMIT 1",
    None, True, "high", 1,
    "Same pattern as canonical_url validation; published = TRUE always since guarded by if: :published?.")
add(F, "index_articles_on_feed_source_url", "articles", "app/services/feeds/assemble_article_markdown.rb:234",
    "found_article = Article.find_by(feed_source_url: link)&.decorate",
    "lookup",
    "SELECT \"articles\".* FROM \"articles\" WHERE \"articles\".\"feed_source_url\" = 'https://x.com/a' LIMIT 1",
    None, False, "high", 0,
    "No published filter: drafts with the same URL may also match, so the partial index does not guarantee uniqueness here.")
add(F, "index_articles_on_feed_source_url", "articles", "app/services/feeds/check_item_previously_imported.rb:20",
    "relation = user.articles\nrelation.where(title: title).or(relation.where(feed_source_url: feed_source_url)).exists?",
    "lookup",
    "SELECT 1 AS one FROM \"articles\" WHERE \"articles\".\"user_id\" = 1 AND (\"articles\".\"title\" = 'x' OR \"articles\".\"feed_source_url\" = 'https://x.com/a') LIMIT 1",
    None, False, "high", 0, "OR with title; no published filter.")
add(F, "index_articles_on_feed_source_url", "articles", "app/services/feeds/import_from_xml.rb:144",
    "scope = user.articles\nscope.where(feed_source_url: candidate_urls).or(scope.where(title: candidate_titles))",
    "lookup",
    "SELECT \"articles\".\"feed_source_url\", \"articles\".\"title\" FROM \"articles\" WHERE \"articles\".\"user_id\" = 1 AND (\"articles\".\"feed_source_url\" IN ('https://x.com/a', 'https://x.com/b') OR \"articles\".\"title\" IN ('x', 'y'))",
    None, False, "high", 0, "Plucked at line 156; multi-value IN list, no published filter. Line 146 is the same without the OR.")

add(F, "index_collections_on_slug_and_organization_id", "collections", "app/models/collection.rb:18",
    "existing_collection = Collection.find_by(slug: slug, organization_id: organization.id)",
    "lookup",
    "SELECT \"collections\".* FROM \"collections\" WHERE \"collections\".\"slug\" = 'x' AND \"collections\".\"organization_id\" = 1 LIMIT 1",
    None, True, "high", 1,
    "Full key; organization_id = const implies organization_id IS NOT NULL. Line 27 repeats as find_by! after RecordNotUnique.")
add(F, "index_collections_on_slug_and_organization_id", "collections", "app/models/collection.rb:43",
    "scope = if organization_id.present?\n  Collection.where(slug: slug, organization_id: organization_id)",
    "lookup",
    "SELECT 1 AS one FROM \"collections\" WHERE \"collections\".\"slug\" = 'x' AND \"collections\".\"organization_id\" = 1 AND \"collections\".\"id\" != 1 LIMIT 1",
    None, True, "high", 0, "Custom slug_uniqueness_within_scope validation (.exists? at line 50); id != only when persisted.")
add(F, "index_collections_on_slug_and_organization_id", "collections", "app/models/article.rb:1119",
    "Collection.joins(organization: :organization_memberships)\n  .where(organization_memberships: { user_id: user.id })\n  .includes(:organization)",
    "inner_join",
    "SELECT \"collections\".* FROM \"collections\" INNER JOIN \"organizations\" ON \"organizations\".\"id\" = \"collections\".\"organization_id\" INNER JOIN \"organization_memberships\" ON \"organization_memberships\".\"organization_id\" = \"organizations\".\"id\" WHERE \"organization_memberships\".\"user_id\" = 1",
    False, True, "high", 0,
    "collections is the OUTER (driving) side; the join on collections.organization_id implies organization_id IS NOT NULL (the index predicate) but the joined tables are organizations/memberships, not collections. includes(:organization) is a separate preload.")

add(F, "index_collections_on_slug_and_user_id", "collections", "app/models/collection.rb:31",
    "Collection.find_or_create_by(slug: slug, user: user, organization_id: nil)",
    "lookup",
    "SELECT \"collections\".* FROM \"collections\" WHERE \"collections\".\"slug\" = 'x' AND \"collections\".\"user_id\" = 1 AND \"collections\".\"organization_id\" IS NULL LIMIT 1",
    None, True, "high", 1, "Full key plus explicit organization_id IS NULL = index predicate.")
add(F, "index_collections_on_slug_and_user_id", "collections", "app/models/collection.rb:45",
    "Collection.where(slug: slug, user_id: user_id, organization_id: nil)",
    "lookup",
    "SELECT 1 AS one FROM \"collections\" WHERE \"collections\".\"slug\" = 'x' AND \"collections\".\"user_id\" = 1 AND \"collections\".\"organization_id\" IS NULL AND \"collections\".\"id\" != 1 LIMIT 1",
    None, True, "high", 0, "Custom uniqueness validation (exists?).")
add(F, "index_collections_on_slug_and_user_id", "collections", "app/models/article.rb:1109",
    "user.collections.where(organization_id: nil).each do |collection|",
    "lookup",
    "SELECT \"collections\".* FROM \"collections\" WHERE \"collections\".\"user_id\" = 1 AND \"collections\".\"organization_id\" IS NULL",
    None, True, "high", 0, "Key prefix only (slug free); predicate explicit. Not a point lookup.")
add(F, "index_collections_on_slug_and_user_id", "collections", "app/controllers/collections_controller.rb:6",
    "@collections = @user.collections.non_empty.order(created_at: :desc)",
    "distinct",
    "SELECT DISTINCT \"collections\".* FROM \"collections\" INNER JOIN \"articles\" ON \"articles\".\"collection_id\" = \"collections\".\"id\" WHERE \"collections\".\"user_id\" = 1 ORDER BY \"collections\".\"created_at\" DESC",
    False, False, "high", 2,
    "non_empty = joins(:articles).distinct (collection.rb:10). collections is the outer side; DISTINCT is over collections.* which contains the PK, so it is redundant only via PK + join fan-out, not via this partial index. Same scope at dashboards_controller.rb:61 and :221 (.count -> COUNT(DISTINCT collections.id)).")

add(F, "index_flag_appeals_on_pending_user_target", "flag_appeals", "app/models/flag_appeal.rb:29",
    "pending_exists = self.class.where(\n  user_id: user_id, appealable_type: appealable_type, appealable_id: appealable_id,\n).pending_review.exists?",
    "lookup",
    "SELECT 1 AS one FROM \"flag_appeals\" WHERE \"flag_appeals\".\"user_id\" = 1 AND \"flag_appeals\".\"appealable_type\" = 'User' AND \"flag_appeals\".\"appealable_id\" = 1 AND \"flag_appeals\".\"status\" IN (0, 1) LIMIT 1",
    None, True, "high", 0,
    "pending_review scope = where(status: %i[open ai_reviewed]) -> status IN (0,1), exactly the index predicate. Only query on this table that uses the key; no joins to flag_appeals found.")

add(F, "idx_lead_submissions_form_user_unique", "lead_submissions", "app/models/lead_submission.rb:5",
    "validates :user_id, uniqueness: { scope: :organization_lead_form_id, ... },\n                    allow_nil: true",
    "lookup",
    "SELECT 1 AS one FROM \"lead_submissions\" WHERE \"lead_submissions\".\"user_id\" = 1 AND \"lead_submissions\".\"organization_lead_form_id\" = 1 LIMIT 1",
    None, True, "high", 0, "allow_nil skips the query when user_id is nil; user_id = const implies IS NOT NULL.")
add(F, "idx_lead_submissions_form_user_unique", "lead_submissions", "app/controllers/lead_submissions_controller.rb:21",
    "existing_submission = form.lead_submissions.find_by(user: current_user)",
    "lookup",
    "SELECT \"lead_submissions\".* FROM \"lead_submissions\" WHERE \"lead_submissions\".\"organization_lead_form_id\" = 1 AND \"lead_submissions\".\"user_id\" = 1 LIMIT 1",
    None, True, "high", 2, "Same find_by at lines 40 and 46.")
add(F, "idx_lead_submissions_form_user_unique", "lead_submissions", "app/controllers/lead_submissions_controller.rb:6",
    "submissions = current_user.lead_submissions.where(organization_lead_form_id: form_ids)\n  .pluck(:organization_lead_form_id, :created_at)",
    "lookup",
    "SELECT \"lead_submissions\".\"organization_lead_form_id\", \"lead_submissions\".\"created_at\" FROM \"lead_submissions\" WHERE \"lead_submissions\".\"user_id\" = 1 AND \"lead_submissions\".\"organization_lead_form_id\" IN (1, 2, 3)",
    None, True, "high", 0, "Key fixed per IN element: at most one row per form id (result is turned into a hash keyed by form id).")

NOTIF_VALID_CODE = "validates :user_id, uniqueness: { scope: %i[organization_id notifiable_id notifiable_type action] }"
# user / action not null
I = "index_notifications_on_user_notifiable_and_action_not_null"
add(F, I, "notifications", "app/services/notifications/reactions/send.rb:59",
    "notification = Notification.find_or_initialize_by(notification_params)",
    "lookup",
    "SELECT \"notifications\".* FROM \"notifications\" WHERE \"notifications\".\"notifiable_type\" = 'Article' AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"subforem_id\" = 1 AND \"notifications\".\"action\" = 'Reaction' AND \"notifications\".\"user_id\" = 1 LIMIT 1",
    None, True, "high", 0,
    "Receiver is a User here (organization branch covers the org index). action = 'Reaction' implies action IS NOT NULL. Extra subforem_id filter. Line 52 uses the same params for delete_all.")
add(F, I, "notifications", "app/services/notifications/milestone/send.rb:52",
    "last_milestone_notification = Notification.find_by(\n  user_id: article.user_id, notifiable_type: \"Article\", notifiable_id: article.id,\n  action: \"Milestone::#{type}::#{@next_milestone}\",",
    "lookup",
    "SELECT \"notifications\".* FROM \"notifications\" WHERE \"notifications\".\"user_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Article' AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"action\" = 'Milestone::Reaction::64' LIMIT 1",
    None, True, "high", 0, "Exact full key; action non-null literal.")
add(F, I, "notifications", "app/services/notifications/co_author/send.rb:27",
    "already_notified = Notification.where(\n  user_id: recipient_ids, notifiable_id: article.id, notifiable_type: \"Article\", action: ACTION,\n).pluck(:user_id)",
    "lookup",
    "SELECT \"notifications\".\"user_id\" FROM \"notifications\" WHERE \"notifications\".\"user_id\" IN (1, 2) AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Article' AND \"notifications\".\"action\" = 'CoAuthor'",
    None, True, "high", 0, "IN list over user_id; plucked user_id values are unique by the index. Followed by upsert_all unique_by this index (line 56).")
add(F, I, "notifications", "app/services/notifications/co_author_invitations/send.rb:16",
    "Notification.find_or_create_by!(user_id: invitation.user_id, notifiable: invitation,\n                                action: INVITED) do |notification|",
    "lookup",
    "SELECT \"notifications\".* FROM \"notifications\" WHERE \"notifications\".\"user_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'CoAuthorInvitation' AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"action\" = 'Invited' LIMIT 1",
    None, True, "high", 1, "Same pattern at co_author_invitations/update.rb:38 (action ACCEPTED). Literal action value assumed.")
add(F, I, "notifications", "app/models/notification.rb:11",
    NOTIF_VALID_CODE,
    "lookup",
    "SELECT 1 AS one FROM \"notifications\" WHERE \"notifications\".\"user_id\" = 1 AND \"notifications\".\"organization_id\" IS NULL AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Article' AND \"notifications\".\"action\" = 'Published' LIMIT 1",
    None, True, "high", 0,
    "Generic validation that serves all four notification indexes; scope value nil becomes IS NULL. For user rows with non-null action this is the full key + predicate (plus organization_id IS NULL). Runs on every Notification.create/save.")
add(F, I, "notifications", "app/services/notifications/notifiable_action/send.rb:74",
    "Notification.upsert_all(\n  notifications_attributes,\n  unique_by: upsert_index,",
    "lookup",
    "INSERT INTO \"notifications\" (\"user_id\",\"notifiable_id\",\"notifiable_type\",\"action\",...) VALUES (1, 1, 'Article', 'Published', ...) ON CONFLICT (\"user_id\",\"notifiable_id\",\"notifiable_type\",\"action\") WHERE (action IS NOT NULL) DO UPDATE SET ... RETURNING \"id\"",
    None, True, "high", 2,
    "Arbiter-index use (ON CONFLICT ... WHERE predicate) rather than a read; choose_upsert_index (line 88) picks this index when action present, else the action_is_null one. Also reactions/send.rb:101 and co_author/send.rb:56.")

I = "index_notifications_on_org_notifiable_and_action_not_null"
add(F, I, "notifications", "app/services/notifications/reactions/send.rb:59",
    "notification = Notification.find_or_initialize_by(notification_params)",
    "lookup",
    "SELECT \"notifications\".* FROM \"notifications\" WHERE \"notifications\".\"notifiable_type\" = 'Article' AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"subforem_id\" = 1 AND \"notifications\".\"action\" = 'Reaction' AND \"notifications\".\"organization_id\" = 1 LIMIT 1",
    None, True, "high", 0, "Branch where receiver is an Organization (line 47). action literal implies NOT NULL.")
add(F, I, "notifications", "app/models/notification.rb:11",
    NOTIF_VALID_CODE,
    "lookup",
    "SELECT 1 AS one FROM \"notifications\" WHERE \"notifications\".\"user_id\" IS NULL AND \"notifications\".\"organization_id\" = 1 AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Article' AND \"notifications\".\"action\" = 'Reaction' LIMIT 1",
    None, True, "high", 0, "Generic validation; for org rows user_id IS NULL is an extra conjunct.")
add(F, I, "notifications", "app/services/notifications/reactions/send.rb:101",
    "upsert_result = Notification.upsert(\n  upsert_attributes,\n  unique_by: upsert_index,",
    "lookup",
    "INSERT INTO \"notifications\" (...) VALUES (...) ON CONFLICT (\"organization_id\",\"notifiable_id\",\"notifiable_type\",\"action\") WHERE (action IS NOT NULL) DO UPDATE SET ... RETURNING \"id\"",
    None, True, "medium", 1,
    "choose_upsert_index (line 111) picks this index for org receivers with action. new_follower/send.rb:40 also queries org+action but without notifiable (key prefix only).")

I = "index_notifications_on_user_notifiable_action_is_null"
add(F, I, "notifications", "app/models/notification.rb:11",
    NOTIF_VALID_CODE,
    "lookup",
    "SELECT 1 AS one FROM \"notifications\" WHERE \"notifications\".\"user_id\" = 1 AND \"notifications\".\"organization_id\" IS NULL AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Comment' AND \"notifications\".\"action\" IS NULL LIMIT 1",
    None, True, "high", 0,
    "Triggered by Notification.create(... action: nil) in new_comment/send.rb:30 and new_badge_achievement/send.rb:14; nil action becomes action IS NULL = index predicate.")
add(F, I, "notifications", "app/controllers/notifications_controller.rb:80",
    "@user.notifications.for_comments.or(@user.notifications.for_mentions)",
    "lookup",
    "SELECT \"notifications\".* FROM \"notifications\" WHERE \"notifications\".\"user_id\" = 1 AND (\"notifications\".\"notifiable_type\" = 'Comment' AND \"notifications\".\"action\" IS NULL OR \"notifications\".\"notifiable_type\" = 'Mention')",
    None, True, "medium", 0, "Range scan (notifiable_id free), predicate explicit only in the first OR branch. Further scopes/pagination appended by caller.")
add(F, I, "notifications", "app/services/mentions/create_all.rb:68",
    "user.notifications.exists?(notifiable_id: notifiable.id, notifiable_type: \"Comment\")",
    "lookup",
    "SELECT 1 AS one FROM \"notifications\" WHERE \"notifications\".\"user_id\" = 1 AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Comment' LIMIT 1",
    None, False, "high", 0, "Key columns minus action; no action restriction, so both user indexes could match.")
add(F, I, "notifications", "app/services/notifications/notifiable_action/send.rb:74",
    "Notification.upsert_all(\n  notifications_attributes,\n  unique_by: upsert_index,",
    "lookup",
    "INSERT INTO \"notifications\" (...) VALUES (...) ON CONFLICT (\"user_id\",\"notifiable_id\",\"notifiable_type\") WHERE (action IS NULL) DO UPDATE SET ... RETURNING \"id\"",
    None, True, "medium", 1, "Used when action is blank (choose_upsert_index line 91). Also reactions/send.rb:121.")

I = "index_notifications_on_org_notifiable_action_is_null"
add(F, I, "notifications", "app/models/notification.rb:11",
    NOTIF_VALID_CODE,
    "lookup",
    "SELECT 1 AS one FROM \"notifications\" WHERE \"notifications\".\"user_id\" IS NULL AND \"notifications\".\"organization_id\" = 1 AND \"notifications\".\"notifiable_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Comment' AND \"notifications\".\"action\" IS NULL LIMIT 1",
    None, True, "high", 0, "Triggered by org Notification.create(action: nil) in new_comment/send.rb:59.")
add(F, I, "notifications", "app/controllers/notifications_controller.rb:90",
    "Notification.for_organization_comments(org_id).or(Notification.for_organization_mentions(org_id))",
    "lookup",
    "SELECT \"notifications\".* FROM \"notifications\" WHERE (\"notifications\".\"organization_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Comment' AND \"notifications\".\"action\" IS NULL AND \"notifications\".\"user_id\" IS NULL OR \"notifications\".\"organization_id\" = 1 AND \"notifications\".\"notifiable_type\" = 'Mention' AND \"notifications\".\"user_id\" IS NULL)",
    None, True, "medium", 1, "Range scan (notifiable_id free). reactions/send.rb:123 picks this index for an upsert.")

add(F, "index_organizations_on_custom_domain", "organizations", "app/lib/org_custom_domain_constraint.rb:56",
    "org = Organization.find_by(custom_domain: normalized_host)",
    "lookup",
    "SELECT \"organizations\".* FROM \"organizations\" WHERE \"organizations\".\"custom_domain\" = 'blog.example.com' LIMIT 1",
    None, True, "high", 0, "Equality with a non-empty host implies custom_domain IS NOT NULL AND <> ''. Request-path routing constraint (cached).")
add(F, "index_organizations_on_custom_domain", "organizations", "app/models/organization.rb:92",
    "validates :custom_domain, uniqueness: { allow_blank: true }, format: { ... }",
    "lookup",
    "SELECT 1 AS one FROM \"organizations\" WHERE \"organizations\".\"custom_domain\" = 'blog.example.com' AND \"organizations\".\"id\" != 1 LIMIT 1",
    None, True, "high", 0, "allow_blank skips nil/''; so predicate implied.")
add(F, "index_organizations_on_tls_subscription_id", "organizations", "", "", "none", "", None, None, "high", 0,
    "tls_subscription_id is only read/written on loaded Organization instances (organizations/*_custom_domain_worker.rb, organization.rb:393); no query filters, joins or groups on it.")

# ---------------- loomio ----------------
L = "loomio"
I = "index_active_push_subscriptions_on_endpoint_digest"
add(L, I, "push_subscriptions", "app/models/push_subscription.rb:19",
    "validates :endpoint_digest,\n          uniqueness: { conditions: -> { where(revoked_at: nil) } },\n          if: :active_endpoint?",
    "lookup",
    "SELECT 1 AS one FROM \"push_subscriptions\" WHERE \"push_subscriptions\".\"endpoint_digest\" = 'abc' AND \"push_subscriptions\".\"revoked_at\" IS NULL LIMIT 1",
    None, True, "high", 0, "conditions: adds revoked_at IS NULL = index predicate.")
add(L, I, "push_subscriptions", "app/services/push_subscription_service.rb:53",
    "subscription = PushSubscription.lock.find_by(endpoint_digest: digest, revoked_at: nil)",
    "lookup",
    "SELECT \"push_subscriptions\".* FROM \"push_subscriptions\" WHERE \"push_subscriptions\".\"endpoint_digest\" = 'abc' AND \"push_subscriptions\".\"revoked_at\" IS NULL LIMIT 1 FOR UPDATE",
    None, True, "high", 0, "Exact key + predicate.")
add(L, I, "push_subscriptions", "app/services/push_subscription_service.rb:24",
    "scope = user.push_subscriptions.active.lock\nscope.find_by!(endpoint_digest: endpoint_digest(endpoint))",
    "lookup",
    "SELECT \"push_subscriptions\".* FROM \"push_subscriptions\" WHERE \"push_subscriptions\".\"user_id\" = 1 AND \"push_subscriptions\".\"revoked_at\" IS NULL AND (expires_at IS NULL OR expires_at > '2026-10-28 00:00:00') AND \"push_subscriptions\".\"endpoint_digest\" = 'abc' LIMIT 1 FOR UPDATE",
    None, True, "high", 0, "active scope supplies revoked_at IS NULL; extra user_id/expires_at filters.")

I = "index_stances_on_poll_id_and_participant_id_and_latest"
add(L, I, "stances", "app/models/poll.rb:199",
    "has_many :stance_voters, -> { merge(Stance.latest) }, through: :stances, source: :participant\n# poll.rb:552  def voters; anonymous? ? User.none : stance_voters; end",
    "inner_join",
    "SELECT \"users\".* FROM \"users\" INNER JOIN \"stances\" ON \"users\".\"id\" = \"stances\".\"participant_id\" WHERE \"stances\".\"poll_id\" = 1 AND \"stances\".\"latest\" = TRUE AND \"stances\".\"revoked_at\" IS NULL",
    True, True, "high", 4,
    "Through-association: users is the outer side, stances the joined side. Join equates stances.participant_id; poll_id is fixed by a constant and latest = TRUE (Stance.latest scope, stance.rb:80) is the index predicate, so each user matches at most one stance: no duplicate users, join reducible to a semi-join. Used by Poll#voters/voter_ids. Same shape: stance_undecided_voters, stance_decided_voters, none_of_the_above_voters (poll.rb:200-202, used at 560/564 and poll_serializer.rb:186), and User#guest_polls (user.rb:103, guest_stances adds latest + inviter_id IS NOT NULL; defined but no caller found).")
add(L, I, "stances", "app/queries/poll_query.rb:64",
    "stances = Stance.latest.undecided.where(participant_id: user.id).select(:poll_id)\nchain = chain.where(anonymous: false, id: stances)",
    "semi_join",
    "SELECT \"polls\".* FROM \"polls\" WHERE ... AND (\"polls\".\"anonymous\" = FALSE AND \"polls\".\"id\" IN (SELECT \"stances\".\"poll_id\" FROM \"stances\" WHERE \"stances\".\"latest\" = TRUE AND \"stances\".\"revoked_at\" IS NULL AND (stances.cast_at IS NULL) AND \"stances\".\"participant_id\" = 1) OR \"polls\".\"anonymous\" = TRUE AND \"polls\".\"id\" IN (SELECT \"anonymous_poll_voters\".\"poll_id\" FROM \"anonymous_poll_voters\" WHERE ...))",
    True, True, "high", 0,
    "stances is the inner side of an IN-subquery on poll_id with participant_id constant and latest = TRUE: subquery output poll_id is unique, so the semi-join can become a plain inner join. Outer chain comes from relevant_to/visible_scope (elided).")
add(L, I, "stances", "app/extras/poll_exporter.rb:79",
    "memberships_by_user_id = Membership.active.where(group_id: @poll.group_id, user_id: @poll.stances.latest.select(:participant_id)).index_by(&:user_id)",
    "semi_join",
    "SELECT \"memberships\".* FROM \"memberships\" WHERE \"memberships\".\"revoked_at\" IS NULL AND \"memberships\".\"group_id\" = 1 AND \"memberships\".\"user_id\" IN (SELECT \"stances\".\"participant_id\" FROM \"stances\" WHERE \"stances\".\"poll_id\" = 1 AND \"stances\".\"latest\" = TRUE AND \"stances\".\"revoked_at\" IS NULL)",
    True, True, "high", 0,
    "Inner subquery over stances with poll_id constant + latest: participant_id output is unique, semi-join on memberships.user_id = stances.participant_id is convertible to a join.")
add(L, I, "stances", "app/controllers/api/v1/announcements_controller.rb:76",
    "model.anonymous? ? model.anonymous_poll_voters.select(:voter_id) : model.stances.latest.select(:participant_id)",
    "semi_join",
    "SELECT \"users\".\"id\" FROM \"users\" WHERE ... AND \"users\".\"deactivated_at\" IS NULL AND \"users\".\"id\" NOT IN (SELECT \"stances\".\"participant_id\" FROM \"stances\" WHERE \"stances\".\"poll_id\" = 1 AND \"stances\".\"latest\" = TRUE AND \"stances\".\"revoked_at\" IS NULL) LIMIT 50",
    True, True, "medium", 0,
    "Passed as exclude_user_ids to UserQuery.invitable_search (user_query.rb:63: where.not(id: ...)), so it is an ANTI-join (NOT IN); inner-side uniqueness holds but matters less for anti-joins. Outer relation varies (relations(model:...)).")
add(L, I, "stances", "app/services/topic_service.rb:136",
    "topic.polls.where(anonymous: false).joins(:stances)\n  .merge(Stance.latest.decided)\n  .pluck(\"stances.participant_id\")",
    "inner_join",
    "SELECT \"stances\".\"participant_id\" FROM \"polls\" INNER JOIN \"stances\" ON \"stances\".\"poll_id\" = \"polls\".\"id\" WHERE \"polls\".\"topic_id\" = 1 AND \"polls\".\"anonymous\" = FALSE AND \"stances\".\"latest\" = TRUE AND \"stances\".\"revoked_at\" IS NULL AND (stances.cast_at IS NOT NULL)",
    False, True, "high", 0,
    "stances is the joined side with latest = TRUE, but the join equates only poll_id; participant_id is free, so the key is not fully bound (many stances per poll).")
add(L, I, "stances", "app/serializers/poll_serializer.rb:299",
    "cache_fetch(:my_stances_by_poll_id, object.id) { Stance.latest.find_by(poll_id: object.id, participant_id: scope[:current_user_id]) }",
    "lookup",
    "SELECT \"stances\".* FROM \"stances\" WHERE \"stances\".\"latest\" = TRUE AND \"stances\".\"revoked_at\" IS NULL AND \"stances\".\"poll_id\" = 1 AND \"stances\".\"participant_id\" = 1 LIMIT 1",
    None, True, "high", 6,
    "Point lookup with full key + predicate. Similar: stances_controller.rb:131, :153 (participant_id IN list), polls_controller.rb:144 and attachment_query.rb:28 and poll.rb:741 (exists? with decided), dev/oatmilk find_by!.")

add(L, "index_subscriptions_on_billing_service_id", "subscriptions", "", "", "none", "", None, None, "high", 0,
    "billing_service_subscription_id is only written (subscriptions/apply_update.rb:75; RecordNotUnique retry at :55) and tested in raw SQL IS NULL in cleanup_service.rb:559. Group joins(:subscription) (group.rb:22-24) joins on subscriptions.id (PK), not this key.")

I = "index_topic_items_on_unique_discussion_root"
add(L, I, "topic_items", "app/models/concerns/has_topic_items.rb:14",
    "topic_items\n  .where(kind: created_topic_item_kind)\n  .order(:id).first",
    "lookup",
    "SELECT \"topic_items\".* FROM \"topic_items\" WHERE \"topic_items\".\"itemable_id\" = 1 AND \"topic_items\".\"itemable_type\" = 'Discussion' AND \"topic_items\".\"kind\" = 'new_discussion' ORDER BY \"topic_items\".\"id\" ASC LIMIT 1",
    None, True, "high", 3,
    "Discussion#created_topic_item_kind = :new_discussion (discussion.rb:144). Full key + predicate; ORDER BY/LIMIT redundant. The has_one :created_topic_item (line 7) has an instance-dependent scope, so it can only be preloaded, never joined/eager_loaded. Callers: topic_item.rb:232-235/281, notification.rb:36, ...")
add(L, I, "topic_items", "app/services/seeded_content_cleanup_service.rb:278",
    "NOT EXISTS (SELECT 1 FROM topic_items WHERE topic_items.topic_id = topics.id ...\n  AND NOT (topic_items.itemable_type = :record_type AND topic_items.itemable_id = RECORD_ID\n  AND topic_items.kind = :root_kind))",
    "semi_join",
    "SELECT \"discussions\".* FROM \"discussions\" INNER JOIN \"topics\" ON ... WHERE ... AND NOT EXISTS (SELECT 1 FROM topic_items WHERE topic_items.topic_id = topics.id AND topic_items.user_id IS NOT NULL AND topic_items.user_id NOT IN (1, 2) AND NOT (topic_items.itemable_type = 'Discussion' AND topic_items.itemable_id = discussions.id AND topic_items.kind = 'new_discussion'))",
    False, False, "high", 0,
    "Anti-join correlated on topic_id; the root-item key appears only negated (excludes the root row). Admin cleanup job (candidate_discussions, line 212).")
add(L, I, "topic_items", "app/models/concerns/has_item_tags.rb:19",
    "WHEN topic_items.kind = 'new_discussion' AND topic_items.itemable_type = 'Discussion' THEN EXISTS (\n  SELECT 1 FROM discussions WHERE discussions.id = topic_items.itemable_id AND discarded_at IS NULL ...",
    "semi_join",
    "SELECT \"topic_items\".* FROM \"topic_items\" WHERE (CASE WHEN topic_items.kind = 'new_discussion' AND topic_items.itemable_type = 'Discussion' THEN EXISTS (SELECT 1 FROM discussions WHERE discussions.id = topic_items.itemable_id AND discarded_at IS NULL LIMIT 1 OFFSET 0) ... ELSE FALSE END)",
    False, True, "medium", 0,
    "topic_items is the OUTER side; EXISTS probes discussions by PK. Branch condition equals the index predicate but the indexed table is not the inner side. tags_visible scope.")

I = "index_topic_items_on_unique_poll_root"
add(L, I, "topic_items", "app/models/concerns/has_topic_items.rb:14",
    "topic_items\n  .where(kind: created_topic_item_kind)\n  .order(:id).first",
    "lookup",
    "SELECT \"topic_items\".* FROM \"topic_items\" WHERE \"topic_items\".\"itemable_id\" = 1 AND \"topic_items\".\"itemable_type\" = 'Poll' AND \"topic_items\".\"kind\" = 'poll_created' ORDER BY \"topic_items\".\"id\" ASC LIMIT 1",
    None, True, "high", 4,
    "Poll#created_topic_item (kind :poll_created from default created_topic_item_kind). Called from outcome.rb:109, stance.rb:209, topic_item.rb:239-247. ORDER BY/LIMIT redundant given index.")
add(L, I, "topic_items", "app/controllers/api/v1/topic_items_controller.rb:134",
    "poll_created = records.find_by!(kind: 'poll_created', itemable: poll)",
    "lookup",
    "SELECT \"topic_items\".* FROM \"topic_items\" WHERE \"topic_items\".\"topic_id\" = 1 AND \"topic_items\".\"kind\" = 'poll_created' AND \"topic_items\".\"itemable_type\" = 'Poll' AND \"topic_items\".\"itemable_id\" = 1 LIMIT 1",
    None, True, "high", 0, "records = TopicItem.where(topic_id: @topic.id) (line 122).")
add(L, I, "topic_items", "app/controllers/api/v1/topic_items_controller.rb:199",
    "TopicItem.where(topic_id: @topic.id, kind: 'poll_created', itemable_type: 'Poll',\n  itemable_id: @topic.polls.kept.where(closed_at: nil).select(:id))",
    "semi_join",
    "SELECT \"topic_items\".* FROM \"topic_items\" WHERE \"topic_items\".\"topic_id\" = 1 AND \"topic_items\".\"kind\" = 'poll_created' AND \"topic_items\".\"itemable_type\" = 'Poll' AND \"topic_items\".\"itemable_id\" IN (SELECT \"polls\".\"id\" FROM \"polls\" WHERE \"polls\".\"topic_id\" = 1 AND \"polls\".\"discarded_at\" IS NULL AND \"polls\".\"closed_at\" IS NULL)",
    False, True, "high", 0,
    "topic_items is the OUTER side (semi-join into polls by PK). Each poll id matches at most one topic_item by this index, so the IN could equally be a join without duplicates, but the indexed table is not the inner side.")
add(L, I, "topic_items", "app/services/seeded_content_cleanup_service.rb:278",
    "AND NOT (topic_items.itemable_type = :record_type AND topic_items.itemable_id = RECORD_ID\n  AND topic_items.kind = :root_kind)",
    "semi_join",
    "SELECT \"polls\".* FROM \"polls\" INNER JOIN \"topics\" ON ... WHERE ... AND NOT EXISTS (SELECT 1 FROM topic_items WHERE topic_items.topic_id = topics.id AND topic_items.user_id IS NOT NULL AND topic_items.user_id NOT IN (1, 2) AND NOT (topic_items.itemable_type = 'Poll' AND topic_items.itemable_id = polls.id AND topic_items.kind = 'poll_created'))",
    False, False, "high", 0, "Anti-join on topic_id; key appears only negated (candidate_polls, line 243).")
add(L, I, "topic_items", "app/services/topic_service.rb:294",
    "TopicItem.joins(\"INNER JOIN topic_items later_comments ON later_comments.topic_id = topic_items.topic_id\")\n  .where(\"topic_items.kind = ?\", 'poll_created') ... .distinct.pluck(:topic_id)",
    "distinct",
    "SELECT DISTINCT \"topic_items\".\"topic_id\" FROM \"topic_items\" INNER JOIN topic_items later_comments ON later_comments.topic_id = topic_items.topic_id WHERE (topic_items.kind = 'poll_created') AND (later_comments.kind = 'new_comment') AND (topic_items.topic_id IS NOT NULL) AND (topic_items.sequence_id > later_comments.sequence_id) AND (topic_items.created_at < later_comments.created_at)",
    False, False, "high", 0,
    "Self-join on topic_id; outer side has kind = 'poll_created' but no itemable_type restriction, joined side is new_comment rows. DISTINCT over topic_id, not the index key.")
add(L, I, "topic_items", "app/models/concerns/has_item_tags.rb:22",
    "WHEN topic_items.kind = 'poll_created' AND topic_items.itemable_type = 'Poll' THEN EXISTS (\n  SELECT 1 FROM polls WHERE polls.id = topic_items.itemable_id AND discarded_at IS NULL ...",
    "semi_join",
    "SELECT \"topic_items\".* FROM \"topic_items\" WHERE (CASE ... WHEN topic_items.kind = 'poll_created' AND topic_items.itemable_type = 'Poll' THEN EXISTS (SELECT 1 FROM polls WHERE polls.id = topic_items.itemable_id AND discarded_at IS NULL LIMIT 1 OFFSET 0) ... ELSE FALSE END)",
    False, True, "medium", 0, "topic_items is the outer side; EXISTS probes polls by PK.")

# ---------------- chatwoot ----------------
C = "chatwoot"
ENT = "Model lives in enterprise/ (not in the shallow checkout: only app/, lib/, db/, config/initializers present); no reference in app/ or lib/."
add(C, "index_campaign_recipients_on_source_id", "campaign_recipients", "", "", "none", "", None, None, "low", 0, ENT)
add(C, "idx_captain_faq_observations_on_conversation_and_suggestion", "captain_faq_observations", "", "", "none", "", None, None, "low", 0, ENT)
add(C, "index_monitor_scans_initial", "conversation_monitor_scans", "", "", "none", "", None, None, "low", 0, ENT)
add(C, "idx_conversation_outcomes_initial_episode", "conversation_outcomes", "", "", "none", "", None, None, "low", 0,
    "ConversationOutcome model and Conversation#conversation_outcomes are defined in enterprise/ (not in checkout). Only lib/seeders references (delete_all by account_id; covering(...).chronological.last), none filtering episode_trigger.")
add(C, "idx_conversation_outcomes_open_episode", "conversation_outcomes", "lib/seeders/reports/assistant_conversation_creator.rb:204",
    "outcome = conversation.conversation_outcomes.covering(resolved_at).chronological.last",
    "lookup",
    "SELECT \"conversation_outcomes\".* FROM \"conversation_outcomes\" WHERE \"conversation_outcomes\".\"conversation_id\" = 1 AND <covering(...) predicate> ORDER BY ... DESC LIMIT 1",
    None, None, "low", 0,
    "Seeder only. Association and covering/chronological scopes are in enterprise/ (not available), so whether ended_at IS NULL is implied cannot be checked; account_id not bound.")

add(C, "index_companies_on_account_and_domain", "companies", "app/models/company.rb:34",
    "validates :domain, uniqueness: { scope: :account_id }, if: -> { domain.present? }",
    "lookup",
    "SELECT 1 AS one FROM \"companies\" WHERE \"companies\".\"domain\" = 'acme.com' AND \"companies\".\"account_id\" = 1 LIMIT 1",
    None, True, "high", 0, "Only when domain present: domain = const implies NOT NULL.")
add(C, "index_companies_on_account_and_domain", "companies", "app/services/contacts/company_association_service.rb:43",
    "Company.find_or_create_by!(account: contact.account, domain: domain) do |company|",
    "lookup",
    "SELECT \"companies\".* FROM \"companies\" WHERE \"companies\".\"account_id\" = 1 AND \"companies\".\"domain\" = 'acme.com' LIMIT 1",
    None, True, "high", 2,
    "Retry find_by at line 48 on RecordNotUnique; same pair in jobs/migration/company_account_batch_job.rb:36/:43.")
add(C, "index_companies_on_account_and_domain", "companies", "app/jobs/companies/fetch_avatars_job.rb:6",
    "companies = account.companies.where.not(domain: [nil, ''])",
    "lookup",
    "SELECT \"companies\".* FROM \"companies\" WHERE \"companies\".\"account_id\" = 1 AND NOT (\"companies\".\"domain\" = '' OR \"companies\".\"domain\" IS NULL)",
    None, True, "high", 0, "Key prefix (account_id) range with explicit domain IS NOT NULL; iterated with find_each/count.")

et_valid = "validates :name, uniqueness: { scope: %i[account_id template_type locale], conditions: -> { where(inbox_id: nil) } }, if: :account_scoped?"
add(C, "index_email_templates_on_account_scope", "email_templates", "app/models/email_template.rb:36", et_valid, "lookup",
    "SELECT 1 AS one FROM \"email_templates\" WHERE \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"account_id\" = 1 AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 AND \"email_templates\".\"inbox_id\" IS NULL LIMIT 1",
    None, True, "high", 0, "Integer enums (layout=0, locale en=0). account_id = const + inbox_id IS NULL = predicate.")
add(C, "index_email_templates_on_account_scope", "email_templates", "app/models/email_template.rb:52",
    "find_by(account: account, inbox: nil, name: BRANDED_LAYOUT_NAME, template_type: :layout, locale: DEFAULT_LOCALE)",
    "lookup",
    "SELECT \"email_templates\".* FROM \"email_templates\" WHERE \"email_templates\".\"account_id\" = 1 AND \"email_templates\".\"inbox_id\" IS NULL AND \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 LIMIT 1",
    None, True, "high", 2, "Called from conversation_reply_mailer.rb:224 and branded_email_layouts_controller.rb:24; also layout_template_for_scope (line 78/83).")
add(C, "index_email_templates_on_account_scope", "email_templates", "app/services/email_templates/db_resolver_service.rb:72",
    "find_template_for(@@model.where(account: Current.account, inbox: nil))\n# relation.find_by(name: name, template_type: @template_type, locale: locale)",
    "lookup",
    "SELECT \"email_templates\".* FROM \"email_templates\" WHERE \"email_templates\".\"account_id\" = 1 AND \"email_templates\".\"inbox_id\" IS NULL AND \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 LIMIT 1",
    None, True, "high", 0, "Mail view resolver; executed per template lookup, looping over locales x names (find_by at line 95).")

add(C, "index_email_templates_on_inbox_scope", "email_templates", "app/models/email_template.rb:37",
    "validates :name, uniqueness: { scope: %i[inbox_id template_type locale] }, if: :inbox_scoped?",
    "lookup",
    "SELECT 1 AS one FROM \"email_templates\" WHERE \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"inbox_id\" = 1 AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 LIMIT 1",
    None, True, "high", 0, "inbox_id = const implies inbox_id IS NOT NULL.")
add(C, "index_email_templates_on_inbox_scope", "email_templates", "app/models/concerns/inbox_branded_email_layoutable.rb:11",
    "email_templates.find_by(name: EmailTemplate::BRANDED_LAYOUT_NAME, template_type: :layout, locale: EmailTemplate::DEFAULT_LOCALE)",
    "lookup",
    "SELECT \"email_templates\".* FROM \"email_templates\" WHERE \"email_templates\".\"inbox_id\" = 1 AND \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 LIMIT 1",
    None, True, "high", 1, "Inbox has_many :email_templates (inbox.rb:72, no scope). Also email_template.rb:77/83.")
add(C, "index_email_templates_on_inbox_scope", "email_templates", "app/services/email_templates/db_resolver_service.rb:66",
    "find_template_for(@@model.where(inbox: Current.inbox))",
    "lookup",
    "SELECT \"email_templates\".* FROM \"email_templates\" WHERE \"email_templates\".\"inbox_id\" = 1 AND \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 LIMIT 1",
    None, True, "high", 0, "Mail view resolver, find_by at line 95.")

add(C, "index_email_templates_on_installation_scope", "email_templates", "app/models/email_template.rb:34",
    "validates :name,\n  uniqueness: { scope: %i[template_type locale], conditions: -> { where(account_id: nil, inbox_id: nil) } },\n  if: :installation_scoped?",
    "lookup",
    "SELECT 1 AS one FROM \"email_templates\" WHERE \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 AND \"email_templates\".\"account_id\" IS NULL AND \"email_templates\".\"inbox_id\" IS NULL LIMIT 1",
    None, True, "high", 0, "conditions supply the exact index predicate.")
add(C, "index_email_templates_on_installation_scope", "email_templates", "app/services/email_templates/db_resolver_service.rb:76",
    "find_template_for(@@model.where(account: nil, inbox: nil))",
    "lookup",
    "SELECT \"email_templates\".* FROM \"email_templates\" WHERE \"email_templates\".\"account_id\" IS NULL AND \"email_templates\".\"inbox_id\" IS NULL AND \"email_templates\".\"name\" = 'base' AND \"email_templates\".\"template_type\" = 0 AND \"email_templates\".\"locale\" = 0 LIMIT 1",
    None, True, "high", 1, "Fallback for every mail render; same at email_template.rb:79/83 (layout_template_for_scope).")

json.dump(S, open(OUT, "w"), indent=1)
for app in ["forem", "loomio", "chatwoot"]:
    rows = [r for r in S if r["app"] == app]
    print(app, len({r["index"] for r in rows}), dict(Counter(r["construct"] for r in rows)),
          sum(1 for r in rows if r["joins_on_index_key"] is True and r["scope_implies_predicate"] is True))
