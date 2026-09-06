import contextlib
import io
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import collect_news as collector
import watch_loop


class ScheduleTests(unittest.TestCase):
    def test_day_gap_from_start_including_failed_attempt(self):
        now = 1800000000
        with patch.object(collector.time, 'time', return_value=now), patch.object(collector, 'is_night', return_value=False):
            for elapsed, expected in [(1499, False), (1500, True), (1501, True)]:
                self.assertEqual(collector.should_run({
                    'lastAttemptAt': now - elapsed, 'last_ok': now - 5000
                })[0], expected)
            self.assertFalse(collector.should_run({'last_ok': now - 1499})[0])
            self.assertTrue(collector.should_run({'last_ok': now - 1500})[0])

    def test_night_gap_is_hourly_cairo_time(self):
        now = 1800000000
        with patch.object(collector.time, 'time', return_value=now), patch.object(collector, 'is_night', return_value=True):
            self.assertFalse(collector.should_run({'last_ok': now - 3599})[0])
            self.assertTrue(collector.should_run({'last_ok': now - 3600})[0])
            self.assertTrue(collector.should_run({'lastAttemptAt': now - 400, 'refreshReq': {'at': (now - 10) * 1000}})[0])
        # 2026-09-06 20:00 Cairo (UTC+3 صيفاً) = 17:00 UTC ليل؛ 05:00 القاهرة = 02:00 UTC نهار
        self.assertTrue(collector.is_night(datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc).timestamp()))
        self.assertFalse(collector.is_night(datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc).timestamp()))
        self.assertFalse(collector.is_night(datetime(2026, 9, 6, 16, 59, tzinfo=timezone.utc).timestamp()))

    def test_slow_tier_parsed_and_defaults_to_fast(self):
        config = 'var centralFeeds = [\n'
        config += ',\n'.join('{ id: "f%d", name: "source", query: "water" }' % i for i in range(10))
        config += ',\n{ id: "s1", name: "slow one", query: \'"x" OR "y"\', tier: "slow" }];\nvar retiredFeeds = [];'
        with patch.object(collector, 'http', return_value=(200, config)):
            feeds, _ = collector.load_feeds()
        self.assertEqual(len(feeds), 11)
        self.assertEqual([f['tier'] for f in feeds if f['id'] == 's1'], ['slow'])
        self.assertTrue(all(f['tier'] == 'fast' for f in feeds if f['id'] != 's1'))

    def test_manual_request_and_served_request(self):
        now = 1800000000
        request_at = (now - 10) * 1000
        job = {'lastAttemptAt': now - 400, 'refreshReq': {'at': request_at}}
        with patch.object(collector.time, 'time', return_value=now):
            self.assertEqual(collector.should_run(job)[2], request_at)
            job['refreshServedAt'] = request_at
            self.assertFalse(collector.should_run(job)[0])

    def test_hourly_sweep_uses_elapsed_time_not_round_counter(self):
        now = 1800000000
        self.assertTrue(collector.sweep_due({}, now))
        self.assertFalse(collector.sweep_due({'lastSweepAt': now - 3599, 'roundNo': 6}, now))
        self.assertTrue(collector.sweep_due({'lastSweepAt': now - 3600, 'roundNo': 1}, now))

    def test_watch_reads_attempt_for_failed_round_backoff(self):
        with patch.object(watch_loop, 'leaf', side_effect=lambda key: {'lastAttemptAt': 123}.get(key)):
            self.assertEqual(watch_loop.read_gate()['lastAttemptAt'], 123)

    def test_display_groups_do_not_become_collection_queries(self):
        config = 'var priorityGroups = [{ slug: "test", nm: "عرض" }];\nvar centralFeeds = [\n'
        config += ',\n'.join('{ id: "f%d", name: "source", query: "water" }' % i for i in range(10))
        config += '];\nvar retiredFeeds = [{ id: "retired", name: "old", query: "old" }];'
        with patch.object(collector, 'http', return_value=(200, config)):
            feeds, _ = collector.load_feeds()
        self.assertEqual(len(feeds), 10)
        self.assertFalse(any(f['id'].startswith('fbgrp_') for f in feeds))

    def run_round(self, elapsed, failed=False):
        now = int(datetime.now(timezone.utc).timestamp())
        job = {'last_ok': now - 2000, 'lastAttemptAt': now - 2000,
               'lastSweepAt': now - elapsed, 'roundNo': 7}
        old = {'title': 'تطهير مصرف زراعي بالمنيا', 'summary': 'تطهير المصرف',
               'url': 'https://example.org/old', 'feedId': 'f', 'feedName': 'test',
               'publishedAt': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
        fresh = dict(old, title='نقص مياه الري في نهايات ترعة بالبحيرة',
                     url='https://example.org/new', publishedAt=datetime.now(timezone.utc).isoformat())
        previous = {'at': (now - 2000) * 1000, 'items': [old], 'count': 1}
        writes = []
        def write(url, method, body, **kwargs):
            writes.append((url, method, body))
            return 200, '{}'
        def read(url, **kwargs):
            return job if url == collector.JOB_URL else previous
        fetched = [{'ok': False, 'why': 'HTTP 503'}] if failed else [{'ok': True, 'body': '<rss/>'}]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(collector, 'DRY', False))
            stack.enter_context(patch.object(collector, 'read_json', side_effect=read))
            stack.enter_context(patch.object(collector, 'write', side_effect=write))
            stack.enter_context(patch.object(collector, 'is_night', return_value=False))
            stack.enter_context(patch.object(collector, 'load_feeds', return_value=([
                {'id': 'f', 'name': 'test', 'query': 'مياه الري', 'tier': 'fast'},
                {'id': 's', 'name': 'slow', 'query': 'بحوث المياه', 'tier': 'slow'}], 'test')))
            fetch = stack.enter_context(patch.object(collector, 'fetch_all', return_value=fetched))
            stack.enter_context(patch.object(collector, 'parse_rss', return_value=[fresh]))
            stack.enter_context(patch.object(collector, 'resolve_rows', return_value=(0, 0, 0)))
            stack.enter_context(patch.object(collector, 'unwrap_cheap', return_value=0))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaises(SystemExit) as end:
                collector.main()
        self.assertEqual(end.exception.code, 1 if failed else 0)
        self.assertIn('lastAttemptAt', writes[0][2])
        fetch.assert_called_once()
        return writes, fetch.call_args.args[0]

    def test_fast_round_keeps_archive_and_publishes_schedule(self):
        writes, urls = self.run_round(1800)
        self.assertIn('when%3A1d', urls[0])
        self.assertEqual(len(urls), 1)   # الزاوية البطيئة لا تدخل الجولة السريعة
        news = [body for url, method, body in writes if url == collector.NEWS_URL and method == 'PUT'][0]
        self.assertEqual(len(news['items']), 2)
        self.assertEqual(news['health']['collectionIntervalSec'], 1500)
        self.assertEqual(news['health']['sweepIntervalSec'], 3600)
        self.assertEqual(news['health']['nextCollectionAt'], (writes[0][2]['lastAttemptAt'] + 1500) * 1000)

    def test_hourly_sweep_does_not_add_fetch_batch(self):
        writes, urls = self.run_round(3601)
        self.assertIn('when%3A7d', urls[0])
        self.assertEqual(len(urls), 2)   # المسحة تجلب البطيئة أيضاً
        self.assertTrue(any('lastSweepAt' in body for url, _, body in writes if url == collector.JOB_URL))

    def test_total_source_failure_preserves_snapshot_and_throttles_retry(self):
        writes, _ = self.run_round(3601, failed=True)
        for url, method, body in writes:
            if url == collector.NEWS_URL:
                self.assertEqual(method, 'PATCH')
                self.assertNotIn('items', body)
                self.assertNotIn('at', body)
        self.assertTrue(any(body.get('fail_streak') == 1 for _, _, body in writes))


if __name__ == '__main__':
    unittest.main()
