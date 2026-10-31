"""Convert the Stack Exchange data dump (stats.stackexchange.com, April 2024, CC BY-SA 4.0) to
CSV for conditional-key mining, streaming the XML (ElementTree iterparse).

Per table, the columns that can take part in keys or conditions: ids and foreign keys,
type/status/class columns, flags, and nullable dates reduced to their presence (closed,
community-owned, deleted). Free text, scores and counts are dropped (they make accidental keys),
and so are timestamps, except one creation date per table, kept as 'created' for the
temporal hold-out. Empty attributes are written as empty fields (null).
Writes CSVDIR/<Table>.csv. Usage: python se_convert.py XMLDIR CSVDIR"""
import csv, os, sys
import xml.etree.ElementTree as ET

TABLES = {
    'Posts': (['Id', 'PostTypeId', 'AcceptedAnswerId', 'ParentId', 'OwnerUserId', 'LastEditorUserId',
               'ContentLicense'], {'ClosedDate': 'Closed', 'CommunityOwnedDate': 'CommunityOwned'}, 'CreationDate'),
    'Votes': (['Id', 'PostId', 'VoteTypeId', 'UserId', 'BountyAmount'], {}, 'CreationDate'),
    'Comments': (['Id', 'PostId', 'UserId', 'ContentLicense'], {'UserDisplayName': 'AnonymousName'}, 'CreationDate'),
    'Badges': (['Id', 'UserId', 'Name', 'Class', 'TagBased'], {}, 'Date'),
    'PostLinks': (['Id', 'PostId', 'RelatedPostId', 'LinkTypeId'], {}, 'CreationDate'),
    'PostHistory': (['Id', 'PostHistoryTypeId', 'PostId', 'RevisionGUID', 'UserId', 'ContentLicense'], {}, 'CreationDate'),
    'Users': (['Id', 'AccountId'], {'WebsiteUrl': 'HasWebsite', 'Location': 'HasLocation'}, 'CreationDate'),
    'Tags': (['Id', 'TagName', 'ExcerptPostId', 'WikiPostId', 'IsModeratorOnly', 'IsRequired'], {}, None),
}


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    for t, (cols, present, created) in TABLES.items():
        n = 0
        with open(os.path.join(dst, f'{t}.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(cols + list(present.values()) + (['created'] if created else []))
            for _, el in ET.iterparse(os.path.join(src, f'{t}.xml')):
                if el.tag != 'row':
                    continue
                a = el.attrib
                w.writerow([a.get(c, '') for c in cols] + [('true' if a.get(c) else 'false') for c in present]
                           + ([a.get(created, '')[:10]] if created else []))
                el.clear(); n += 1
        print(t, n, flush=True)


if __name__ == '__main__':
    main()
