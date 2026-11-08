#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""離線回歸測試：不需要連線抓取新聞。"""
import os
import json
import sys
import unittest
import re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scraper


def row(store, offer, start, end, url, title='測試優惠'):
    return {
        'store': store,
        'offer': offer,
        'status': 'active',
        'start_date': start,
        'end_date': end,
        'date_text': f'{start}～{end}' if start and end else '活動日期尚待確認',
        'schedule_note': '',
        'article_title': title,
        'article_url': url,
        'source_urls': [url],
        'published': '2026-10-23',
        'needs_check': True,
        'category': 'coffee',
    }


class DealDedupRegressionTests(unittest.TestCase):
    # 舊版快照與回歸案例以 2026-10-23 為測試基準；固定日期避免測試隨日曆推移失效。
    def setUp(self):
        self._old_today = scraper.TODAY
        from datetime import date
        scraper.TODAY = date(2026, 10, 23)

    def tearDown(self):
        scraper.TODAY = self._old_today

    def test_combo_and_specific_711_americano_merge_to_specific_label(self):
        data = [
            row('7-ELEVEN', '大杯美式／拿鐵：2 杯 66 元', '2026-10-21', '2026-10-25', 'https://news.example/a'),
            row('7-ELEVEN', '大杯美式2杯66元，6折（原價55元、特價33元）', '2026-10-21', '2026-10-25', 'https://news.example/b'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertIn('美式', out[0]['offer'])
        self.assertNotIn('／拿鐵', out[0]['offer'])
        self.assertEqual(len(out[0]['source_urls']), 2)

    def test_same_deal_period_variants_merge_and_choose_current_later_window(self):
        data = [
            row('7-ELEVEN', '7-ELEVEN APP 10 杯組：特大美式 360 元', '2026-10-14', '2026-10-27', 'https://news.example/a'),
            row('7-ELEVEN', '特大杯美式10杯360元，6折（原價60元、特價36元）', '2026-10-22', '2026-10-31', 'https://news.example/b'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]['start_date'], out[0]['end_date']), ('2026-10-22', '2026-10-31'))
        self.assertIn('特大杯美式10杯360元', out[0]['offer'])

    def test_bulk_deal_cross_labeled_in_old_data_returns_to_meilianshe(self):
        data = [
            row('全家', '大杯鮮奶拿鐵100杯2400元，約4.4折（原價55元、特價24元）', '', '2026-10-31', 'https://news.example/a', '颱風假咖啡優惠！萊爾富買一送一 7-11美式2杯66元'),
            row('美廉社', '美廉社 APP 隨買隨取：大杯濃萃鮮奶拿鐵 100 杯 2,400 元', '2026-10-22', '2026-10-27', 'https://news.example/b', '美廉社20週年咖啡優惠'),
            row('美廉社', '大杯鮮奶拿鐵：100 杯 2,400 元，平均 24 元', '2026-10-14', '2026-10-27', 'https://news.example/c', '四大超商咖啡優惠'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '美廉社')
        self.assertEqual((out[0]['start_date'], out[0]['end_date']), ('2026-10-22', '2026-10-27'))

    def test_same_promotion_at_different_brands_is_not_merged(self):
        data = [
            row('7-ELEVEN', 'CITY CAFE 大杯美式2杯66元', '2026-10-21', '2026-10-25', 'https://news.example/a'),
            row('全家', "Let's Cafe 大杯美式2杯66元", '2026-10-21', '2026-10-25', 'https://news.example/b'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 2)
        self.assertEqual({x['store'] for x in out}, {'7-ELEVEN', '全家'})

    def test_super_size_and_large_size_are_distinct(self):
        data = [
            row('7-ELEVEN', '大杯美式10杯360元', '2026-10-22', '2026-10-31', 'https://news.example/a'),
            row('7-ELEVEN', '特大杯美式10杯360元', '2026-10-22', '2026-10-31', 'https://news.example/b'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 2)

    def test_multiple_prices_in_one_article_split_without_splitting_thousands(self):
        text = '美廉社歡慶20週年，美廉社APP隨買隨取即日起至10月27日，大杯濃萃美式咖啡100杯只要2,000元，大杯濃萃鮮奶拿鐵100杯只要2,400元'
        parts = scraper.split_compound_offer(text)
        self.assertEqual(len(parts), 2)
        self.assertTrue(any('美式' in x and '2,000元' in x for x in parts))
        self.assertTrue(any('拿鐵' in x and '2,400元' in x for x in parts))

    def test_generic_bulk_coffee_narrative_is_filtered(self):
        self.assertTrue(scraper.is_non_offer_record({'offer': '美廉社咖啡100杯只要2,000元'}))

    def test_article_title_removes_misreported_three_cups_77_only(self):
        title = '光復節優惠：7-11 3 杯 77 元、全家買 2 送 2、萊爾富買 10 送 10'
        cleaned = scraper.sanitize_title(title)
        self.assertNotIn('3 杯 77 元', cleaned)
        self.assertIn('全家買 2 送 2', cleaned)
        self.assertIn('萊爾富買 10 送 10', cleaned)

    def test_remove_false_three_cups_77_offer(self):
        data = [row('7-ELEVEN', '大杯美式／拿鐵 3 杯 77 元', '2026-10-21', '2026-10-25', 'https://news.example/false')]
        self.assertEqual(scraper.deduplicate_deals(data), [])

    def test_remove_three_cups_77_but_keep_two_cups_66_from_same_paragraph(self):
        data = [row('7-ELEVEN', '大杯美式／拿鐵 2 杯 66 元、3 杯 77 元', '2026-10-21', '2026-10-25', 'https://news.example/mixed')]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertIn('2 杯 66 元', out[0]['offer'])
        self.assertNotIn('3 杯 77 元', out[0]['offer'])

    def test_do_not_remove_other_77_dollar_promotion(self):
        data = [row('7-ELEVEN', '大杯拿鐵 2 杯 77 元', '2026-10-21', '2026-10-25', 'https://news.example/two-77')]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertIn('2 杯 77 元', out[0]['offer'])

    def test_correct_ambiguous_two_for_two_to_family_when_same_source_has_explicit_evidence(self):
        url = 'https://news.example/shared-source'
        data = [
            row('7-ELEVEN', '特濃美式／拿鐵買 2 送 2', '2026-10-23', '2026-10-27', url),
            row('全家', '全家大杯特濃美式與拿鐵買2送2', '2026-10-23', '2026-10-27', url),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '全家')


    def test_explicit_store_name_beats_product_fingerprint(self):
        self.assertEqual(scraper.find_store('7-ELEVEN 大杯特濃美式買1送1'), '7-ELEVEN')
        self.assertEqual(scraper.find_store('萊爾富特大杯特濃美式買1送1'), '萊爾富')
        self.assertEqual(scraper.find_store('萊爾富濃萃美式買1送1'), '萊爾富')



    def test_cti_section_heading_switches_context_from_family_to_hilife(self):
        article = {
            'title': '中天新聞｜超商咖啡優惠整理',
            'url': scraper.URL_CTINEWS,
            'published': '2026-10-22',
        }
        fetched = {
            'ok': True,
            'title': article['title'],
            'final_url': article['url'],
            'published': article['published'],
            'lines': [
                '全家',
                "Let's Tea 任選第二杯 8 折",
                '萊爾富',
                '10/14～11/10抹茶歐蕾、焙茶歐蕾任選買1送1',
                '即日起～11/10，大杯拿鐵6杯280元、55杯2255元、80杯3080元',
            ],
        }
        out = scraper.extract_article_deals(article, fetched)
        tea = [x for x in out if "Let's Tea" in x['offer']]
        bulk = [x for x in out if '大杯拿鐵' in x['offer']]
        matcha = [x for x in out if '抹茶歐蕾' in x['offer'] or '焙茶歐蕾' in x['offer']]
        self.assertTrue(tea)
        self.assertTrue(all(x['store'] == '全家' for x in tea))
        self.assertTrue(bulk)
        self.assertTrue(all(x['store'] == '萊爾富' for x in bulk))
        self.assertTrue(matcha)
        self.assertTrue(all(x['store'] == '萊爾富' for x in matcha))

    def test_cleaned_snapshot_has_correct_hilife_store_labels(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        source = scraper.URL_CTINEWS
        wrong = [
            x for x in snapshot['deals']
            if x.get('article_url') == source
            and x.get('store') == '全家'
            and any(s in x.get('offer', '') for s in ['大杯拿鐵 6杯280元', '大杯拿鐵 55杯2255元', '大杯拿鐵 80杯3080元', '大杯特濃拿鐵', '大杯特濃美式', '大杯美式 6杯230元', '抹茶歐蕾買1送1'])
        ]
        self.assertEqual(wrong, [])

    def test_cti_hilife_bulk_price_records_are_reassigned_from_family(self):
        url = scraper.URL_CTINEWS
        offers = [
            '大杯拿鐵 6杯280元', '大杯拿鐵 55杯2255元', '大杯拿鐵 80杯3080元',
            '大杯特濃拿鐵 6杯330元', '大杯特濃拿鐵 55杯2690元', '大杯特濃拿鐵 80杯3640元',
            '大杯美式 6杯230元', '大杯美式 55杯1850元', '大杯美式 80杯2520元',
            '大杯特濃美式 6杯280元', '大杯特濃美式 55杯2255元', '大杯特濃美式 80杯3100元',
            '抹茶歐蕾買1送1，5折（原價70元、特價35元）',
        ]
        data = [row('全家', offer, '2026-10-21', '2026-11-10', url) for offer in offers]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), len(offers))
        self.assertTrue(all(x['store'] == '萊爾富' for x in out))

    def test_cti_hilife_source_correction_does_not_relabel_family_lets_tea(self):
        data = [row('全家', "Let's Tea 任選第二杯8折", '2026-10-22', '2026-11-10', scraper.URL_CTINEWS)]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '全家')

    def test_weekday_coffee_day_fingerprint_corrects_stale_711_context(self):
        article = {
            'title': '中天新聞｜超商咖啡優惠整理',
            'url': scraper.URL_CTINEWS,
            'published': '2026-10-22',
        }
        fetched = {
            'ok': True,
            'title': article['title'],
            'final_url': article['url'],
            'published': article['published'],
            'lines': [
                '7-ELEVEN 特大杯美式10杯360元',
                '週三咖啡日，大單品、大特濃咖啡同品項+10元多1杯',
                '萊爾富特大杯特濃美式買1送1',
            ],
        }
        out = scraper.extract_article_deals(article, fetched)
        weekly = [x for x in out if '週三咖啡日' in x.get('schedule_note', '') or '週三咖啡日' in x.get('offer', '')]
        hilife = [x for x in out if '萊爾富特大杯特濃美式' in x['offer']]
        self.assertEqual(len(weekly), 1)
        self.assertEqual(weekly[0]['store'], '全家')
        self.assertEqual(len(hilife), 1)
        self.assertEqual(hilife[0]['store'], '萊爾富')

    def test_old_mislabelled_weekday_record_is_reassigned_to_family(self):
        data = [row(
            '7-ELEVEN',
            '週三咖啡日，大單品、大特濃咖啡同品項+10元多1杯',
            '2026-10-14', '2026-10-27', scraper.URL_CTINEWS,
        )]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '全家')


    def test_weekday_coffee_day_wording_variants_merge(self):
        url = scraper.URL_CTINEWS
        data = [
            row('7-ELEVEN', '週三咖啡日，大單品、大特濃咖啡同品項+10元多1杯', '2026-10-14', '2026-10-27', url),
            row('全家', '全家推出「週三咖啡日」，購買大單品或大特濃咖啡，享同品項加10元多1杯優惠', '', '', url),
        ]
        out = scraper.deduplicate_deals(data)
        weekly = [x for x in out if x.get('store') == '全家' and '咖啡日' in x.get('schedule_note', '')]
        self.assertEqual(len(weekly), 1)
        self.assertEqual(weekly[0]['store'], '全家')
        self.assertEqual(weekly[0]['schedule_note'], '每週三｜咖啡日')
        self.assertEqual(len(weekly[0]['source_urls']), 1)

    def test_identical_offer_in_separate_nonoverlapping_periods_is_preserved(self):
        data = [
            row('7-ELEVEN', '大杯美式 10 杯組 360 元', '2026-10-01', '2026-10-10', 'https://news.example/period-a'),
            row('7-ELEVEN', '大杯美式 10 杯組 360 元', '2026-10-20', '2026-10-31', 'https://news.example/period-b'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 2)
        self.assertEqual({x['end_date'] for x in out}, {'2026-10-10', '2026-10-31'})

    def test_ambiguous_cti_manual_seeds_not_wrongly_assigned_to_711(self):
        data = [row('7-ELEVEN', '大杯美式 7 杯組 255 元', '2026-10-15', '2026-11-30', scraper.URL_CTINEWS, '快來喝！超商咖啡寄杯買30送30') ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '萊爾富')


    def test_short_store_headings_survive_line_split_and_noise_filter(self):
        lines = scraper.split_text_to_lines("全家\n萊爾富\n7-ELEVEN")
        self.assertIn("全家", lines)
        self.assertIn("萊爾富", lines)
        self.assertFalse(scraper.is_noise("全家"))
        self.assertFalse(scraper.is_noise("萊爾富"))

    def test_exclusive_product_fingerprint_repairs_stale_store_labels(self):
        data = [
            row('萊爾富', '指定星沁爽系列特大杯單一優惠價99元', '2026-09-09', '2026-11-03', scraper.URL_CTINEWS),
            row('7-ELEVEN', '酷繽果系列任選買1送1', '2026-10-19', '2026-10-21', scraper.URL_CTINEWS),
            row('萊爾富', '不可思議咖啡奶霜飲品優惠價99元', '2026-10-14', '2026-10-27', scraper.URL_CTINEWS),
        ]
        out = scraper.deduplicate_deals(data)
        by_offer = {x['offer']: x['store'] for x in out}
        self.assertEqual(by_offer['指定星沁爽系列特大杯單一優惠價99元'], '星巴克')
        self.assertEqual(by_offer['酷繽果系列任選買1送1'], '全家')
        self.assertEqual(by_offer['不可思議咖啡奶霜飲品優惠價99元'], '7-ELEVEN')

    def test_unmatched_quote_sidebar_fragment_is_filtered(self):
        item = row('小北百貨', '珍奶10杯360元」霜淇淋', '', '', 'https://news.example/sidebar')
        self.assertTrue(scraper.is_non_offer_record(item))
        self.assertEqual(scraper.deduplicate_deals([item]), [])

    def test_curated_hilife_bulk_prices_include_all_known_6_55_80_cup_variants(self):
        cur = scraper.curated_deals()
        expected = {
            '大杯拿鐵 6 杯 280 元', '大杯拿鐵 55 杯 2,255 元', '大杯拿鐵 80 杯 3,080 元',
            '大杯美式 6 杯 230 元', '大杯美式 55 杯 1,850 元', '大杯美式 80 杯 2,520 元',
            '大杯特濃美式 6 杯 280 元', '大杯特濃美式 55 杯 2,255 元', '大杯特濃美式 80 杯 3,100 元',
            '大杯特濃拿鐵 6 杯 330 元', '大杯特濃拿鐵 55 杯 2,690 元', '大杯特濃拿鐵 80 杯 3,640 元',
        }
        found = {x['offer'] for x in cur if x['store'] == '萊爾富'}
        self.assertTrue(expected.issubset(found))

    def test_explicit_brand_wins_over_exclusive_product_phrase(self):
        self.assertEqual(scraper.find_store('7-ELEVEN 不可思議咖啡買一送一'), '7-ELEVEN')
        self.assertEqual(scraper.find_store('萊爾富特大特濃美式買一送一'), '萊爾富')

    def test_blacklist_only_removes_three_cup_77_from_multi_offer(self):
        line = '大杯美式 2 杯 66 元、3 杯 77 元'
        parts = scraper._expand_offer_text(line)
        self.assertTrue(any('2 杯 66 元' in x for x in parts))
        self.assertFalse(any('3 杯 77 元' in x for x in parts))


    def test_snapshot_has_all_15_confirmed_hilife_bulk_and_7_cup_deals(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        normalized = [(x.get('store'), re.sub(r'\s+', '', x.get('offer', ''))) for x in snapshot['deals']]
        expected = [
            '大杯美式7杯組255元', '大杯拿鐵7杯組310元', '珍珠奶茶7杯組315元',
            '大杯美式6杯230元', '大杯美式55杯1850元', '大杯美式80杯2520元',
            '大杯拿鐵6杯280元', '大杯拿鐵55杯2255元', '大杯拿鐵80杯3080元',
            '大杯特濃美式6杯280元', '大杯特濃美式55杯2255元', '大杯特濃美式80杯3100元',
            '大杯特濃拿鐵6杯330元', '大杯特濃拿鐵55杯2690元', '大杯特濃拿鐵80杯3640元',
        ]
        for offer in expected:
            self.assertIn(('萊爾富', offer), normalized, offer)

    def test_snapshot_has_correct_hilife_four_drink_promo_and_absorbed_single_item_duplicate(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        combo = [x for x in snapshot['deals'] if all(term in x.get('offer', '') for term in ('特大美式', '特大特濃美式', '特大重乳拿鐵', '大杯燕麥奶拿鐵')) and re.search(r'買\s*[一1]\s*送\s*[一1]', x.get('offer', ''))]
        self.assertEqual(len(combo), 1)
        self.assertEqual(combo[0]['store'], '萊爾富')
        self.assertTrue(any('tw.stock.yahoo.com/news/' in u for u in combo[0].get('source_urls', [])))
        self.assertFalse(any(x.get('store') == '小北百貨' and '特大美式' in x.get('offer', '') and '特大重乳拿鐵' in x.get('offer', '') for x in snapshot['deals']))
        self.assertFalse(any(x.get('store') == '萊爾富' and x.get('offer', '').startswith('特大杯重乳拿鐵買1送1') for x in snapshot['deals']))
        self.assertFalse(any(x.get('store') == '萊爾富' and '重乳拿鐵與燕麥奶拿鐵等熱門飲品' in x.get('offer', '') for x in snapshot['deals']))

    def test_snapshot_has_no_blacklisted_promo_or_unmatched_quote_sidebar(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        for item in snapshot['deals']:
            self.assertFalse(scraper.is_blacklisted_promotion(item.get('offer', '')), item.get('offer', ''))
            self.assertFalse(scraper.is_blacklisted_promotion(item.get('article_title', '')), item.get('article_title', ''))
            text = item.get('offer', '')
            self.assertFalse(('」' in text and '「' not in text) or ('』' in text and '『' not in text), text)


    def test_jsonld_parser_is_preserved(self):
        self.assertTrue(callable(scraper.parse_jsonld_article_bodies))


    def test_same_hi_life_smoothie_flat_price_with_different_exclusions_merges(self):
        data = [
            row('萊爾富', '果昔全系列均一價69元（不含芋頭戀乳、芋仔憨吉）', '2026-10-14', '2026-11-10', 'https://news.example/smoothie-a'),
            row('萊爾富', '10月14日至11月10日果昔全系列均一價69元(不含芋頭戀乳和芋仔憨吉)', '2026-10-14', '2026-11-10', 'https://news.example/smoothie-b'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]['source_urls']), 2)
        self.assertEqual(scraper._promotion_signature(scraper._normalise_offer_core(data[0]['offer'])), 'direct-price:69')

    def test_starbucks_starquench_99_dollar_variants_merge_and_keep_known_dates(self):
        data = [
            row('星巴克', '2026/9/9~11/3，草莓巴西莓風味檸檬/椰奶/冰雪星沁爽、芒果火龍果檸檬/椰奶/冰雪星沁爽、蘋果山竹風味爆爆檸檬/椰奶星沁爽，特大杯單一價99元', '2026-09-09', '2026-11-03', 'https://news.example/star-a'),
            row('星巴克', '除了每週一、二的信用卡優惠，星巴克至 11 月 3 日還有指定星沁爽系列特大杯單一優惠價 99 元活動，適用飲品與門市依官方公告為準', '', '2026-11-03', 'https://news.example/star-b'),
            row('星巴克', '星巴克星沁爽特大杯 99 元', '', '', 'https://news.example/star-c'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]['start_date'], out[0]['end_date']), ('2026-09-09', '2026-11-03'))
        self.assertEqual(len(out[0]['source_urls']), 3)

    def test_mixed_familymart_softserve_and_coolbanggo_line_does_not_merge_into_single_coffee(self):
        mixed = row('7-ELEVEN', '冰冰仙草蜜/燒燒仙草任選、單品美式/拿鐵同品項、霜淇淋系列任選、酷繽果系列任選買1送1', '2026-10-19', '2026-10-21', scraper.URL_CTINEWS)
        single = row('全家', '大杯特濃美式買 1 送 1', '2026-10-19', '2026-10-21', 'https://news.example/family-single')
        out = scraper.deduplicate_deals([mixed, single])
        self.assertEqual(len(out), 2)
        mixed_rows = [x for x in out if '酷繽果' in x['offer']]
        single_rows = [x for x in out if '特濃美式' in x['offer']]
        self.assertEqual(len(mixed_rows), 1)
        self.assertEqual(mixed_rows[0]['store'], '全家')
        self.assertEqual(len(single_rows), 1)

    def test_snapshot_has_no_duplicate_hilife_smoothie_or_starquench_deals(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        smoothies = [x for x in snapshot['deals'] if x.get('store') == '萊爾富' and '果昔' in x.get('offer', '') and '69' in x.get('offer', '')]
        stars = [x for x in snapshot['deals'] if x.get('store') == '星巴克' and '星沁爽' in x.get('offer', '') and '99' in x.get('offer', '')]
        self.assertEqual(len(smoothies), 1, [x.get('offer') for x in smoothies])
        self.assertEqual(len(stars), 1, [x.get('offer') for x in stars])


    def test_sidebar_markers_are_cut_and_noise_record_is_removed(self):
        dirty = row(
            '萊爾富',
            '大杯特濃拿鐵■ 優惠：同品項買30送30 【延伸閱讀】 跑咖別漏「這1間」',
            '2026-10-14', '2026-11-10', scraper.URL_COSMO,
        )
        self.assertEqual(scraper.deduplicate_deals([dirty]), [])
        cleanable = row(
            '萊爾富',
            '萊爾富大杯特濃美式買30送30 ■ 活動時間：10/14-11/10 ■ 品項：大杯特濃美式',
            '2026-10-14', '2026-11-10', scraper.URL_COSMO,
        )
        out = scraper.deduplicate_deals([cleanable])
        self.assertEqual(len(out), 1)
        self.assertNotIn('■', out[0]['offer'])
        self.assertNotIn('延伸閱讀', out[0]['offer'])

    def test_unmatched_closing_quote_is_rejected_instead_of_becoming_a_ghost_offer(self):
        dirty = row('小北百貨', '珍奶10杯360元」霜淇淋', '2026-10-22', '2026-10-31', scraper.URL_YAHOO_GENERAL)
        self.assertTrue(scraper.has_unmatched_closing_quote(dirty['offer']))
        self.assertEqual(scraper.deduplicate_deals([dirty]), [])

    def test_editorial_prefix_is_filtered_even_when_shorter_than_55_chars(self):
        samples = [
            '如果每天幾乎都會買咖啡，7-ELEVEN 這次另外準備方案',
            '如果只是連假出遊途中想買咖啡',
        ]
        for text in samples:
            self.assertTrue(scraper.is_non_offer_record({'offer': text}), text)
            self.assertEqual(scraper.deduplicate_deals([row('7-ELEVEN', text, '2026-10-20', '2026-10-31', scraper.URL_APPLE_328076)]), [])

    def test_hilife_heavy_milk_latte_overrides_stale_wrong_store_label(self):
        offer = '特大美式／特大特濃美式／特大重乳拿鐵／大杯燕麥奶拿鐵，同品項買 1 送 1'
        self.assertEqual(scraper.infer_exclusive_store(offer), '萊爾富')
        dirty = row(
            '小北百貨', offer, '2026-10-14', '2026-11-10',
            'https://news.example/hilife-holiday',
            '4大超商光復節連假咖啡優惠整理',
        )
        out = scraper.deduplicate_deals([dirty])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '萊爾富')

    def test_hilife_combo_offer_absorbs_duplicate_single_item_offer(self):
        url_a = 'https://news.example/hilife-single'
        url_b = 'https://news.example/hilife-combo'
        url_c = 'https://news.example/hilife-summary'
        data = [
            row('萊爾富', '特大杯重乳拿鐵買1送1，5折（原價85元、特價43元）', '2026-10-14', '2026-11-10', url_a),
            row('萊爾富', '特大美式／特大特濃美式／特大重乳拿鐵／大杯燕麥奶拿鐵，同品項買 1 送 1', '2026-10-14', '2026-11-10', url_b),
            row('萊爾富', '重乳拿鐵與燕麥奶拿鐵等熱門飲品「買 1 送 1', '', '2026-11-10', url_c),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 1)
        self.assertIn('特大美式／特大特濃美式', out[0]['offer'])
        self.assertIn('特大重乳拿鐵', out[0]['offer'])
        self.assertEqual(set(out[0]['source_urls']), {url_a, url_b, url_c})

    def test_combo_component_dedup_requires_matching_store_promo_and_dates(self):
        combo = '特大美式／特大特濃美式／特大重乳拿鐵／大杯燕麥奶拿鐵，同品項買 1 送 1'
        self.assertTrue(scraper._offer_is_component_of_combo('特大杯重乳拿鐵買1送1', combo))
        self.assertFalse(scraper._offer_is_component_of_combo('特大杯重乳拿鐵買2送2', combo))
        shorthand_bulk_combo = '10/16～10/31大杯特濃美式/拿鐵同品項買30送30'
        self.assertTrue(scraper._offer_is_component_of_combo('大杯特濃拿鐵買30送30', shorthand_bulk_combo))
        dated_list = '美廉社APP即日起至10/27，大杯美式、特大杯美式、大杯鮮奶拿鐵同品項買5送5'
        self.assertFalse(scraper._offer_is_component_of_combo('至 10/27 美廉社：APP 指定咖啡買 5 送 5', dated_list))

    def test_heavy_milk_latte_fingerprint_does_not_capture_711_thick_milk_latte(self):
        self.assertEqual(scraper.infer_exclusive_store('特大杯厚乳拿鐵買2送1'), '')
        self.assertEqual(scraper.infer_store_from_product('特大杯厚乳拿鐵買2送1'), '7-ELEVEN')

    def test_cafe_reserve_and_incredible_coffee_identify_711(self):
        text = '+? CAFE RESERVE 11/1前購買不可思議咖啡奶霜飲品即可免費獲得萬聖節拉花體驗'
        self.assertEqual(scraper.find_explicit_store(text), '7-ELEVEN')
        self.assertEqual(scraper.find_store(text), '7-ELEVEN')
        row_data = row('品牌待確認', text, '2026-10-14', '2026-10-27', scraper.URL_CTINEWS)
        out = scraper.deduplicate_deals([row_data])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['store'], '7-ELEVEN')

    def test_global_summary_does_not_inherit_previous_store_context(self):
        article = {
            'title': '星巴克本週優惠整理',
            'url': scraper.URL_YAHOO_GENERAL,
            'published': '2026-10-22',
        }
        fetched = {
            'ok': True, 'title': article['title'], 'final_url': article['url'],
            'published': article['published'],
            'lines': [
                '星巴克',
                '星沁爽特大杯99元',
                '光復連假將至，四大超商優惠再加碼，包括咖啡買1送1',
                '特大杯咖啡買1送1',
            ],
        }
        out = scraper.extract_article_deals(article, fetched)
        trailing = [x for x in out if x['offer'] == '特大杯咖啡買1送1']
        self.assertEqual(len(trailing), 1)
        self.assertEqual(trailing[0]['store'], '品牌待確認')


    def test_editorial_only_buying_guide_fragments_are_filtered(self):
        samples = [
            '每天固定喝一杯：可以優先看 7-ELEVEN 1,010 元寄杯方案，其中大杯美式 38 杯平均約 27 元，單杯價格最低',
            '不想囤大量咖啡，全家 10 元多一杯則最有彈性',
            '不過要注意，這不代表單杯咖啡只要 5 元，而是以原價 90 元購買第一杯後，第二杯相當於加 5 元，實際平均每杯仍是 47.5 元',
            '萊爾富這週有兩種不同杯數的咖啡寄杯優惠，分別是短期買 10 送 10，以及適合長期囤杯的買 30 送 30',
            '這組優惠的優點是不用一次購買大量寄杯券，適合平常固定購買特濃咖啡的人',
            '美廉社大杯美式平均一杯只要 22.5 元，不用一次購買數十杯，也能享有相當划算的價格',
            '星巴克也推出促銷，多款季節風味飲品以特大杯單一價99元提供，各品牌另設限期或限定品項活動',
        ]
        for i, offer in enumerate(samples):
            with self.subTest(offer=offer):
                self.assertTrue(scraper.is_non_offer_record({'offer': offer}), offer)
                self.assertEqual(scraper.deduplicate_deals([row('品牌待確認', offer, '', '', f'https://news.example/editorial-only-{i}')]), [])

    def test_real_promotions_wrapped_in_editorial_language_are_cleaned_not_lost(self):
        scenarios = [
            ('美廉社', '想喝便宜美式咖啡：美廉社大杯美式買 5 送 5，平均一杯 22.5 元', '美廉社大杯美式買 5 送 5'),
            ('OKmart', '咖啡品項可以看大杯西西里咖啡，單杯優惠價 39 元，一次買兩杯則是 69 元，平均一杯約 35 元', '大杯西西里咖啡'),
            ('全家', '以及全家特濃咖啡買 2 送 2都很適合連假和家人朋友一起買', '全家特濃咖啡買 2 送 2'),
        ]
        for i, (store, narrative, expected_fragment) in enumerate(scenarios):
            with self.subTest(narrative=narrative):
                out = scraper.deduplicate_deals([row(store, narrative, '', '', f'https://news.example/editorial-core-{i}')])
                self.assertEqual(len(out), 1)
                self.assertIn(expected_fragment, out[0]['offer'])
                self.assertNotRegex(out[0]['offer'], r'^(?:想喝便宜|咖啡品項可以看|以及)')
                self.assertNotRegex(out[0]['offer'], r'都很適合連假|家人朋友一起買')

    def test_editorial_filters_do_not_drop_real_promotion_mechanisms(self):
        samples = [
            ('萊爾富', '特大重乳拿鐵買1送1'),
            ('美廉社', '美廉社大杯美式買5送5'),
            ('全家', '全家特濃咖啡買2送2'),
        ]
        for i, (store, offer) in enumerate(samples):
            with self.subTest(offer=offer):
                self.assertFalse(scraper.is_non_offer_record({'offer': offer}), offer)
                self.assertEqual(len(scraper.deduplicate_deals([row(store, offer, '2026-10-23', '2026-10-31', f'https://news.example/real-{i}')])), 1)

    def test_frontend_has_one_shared_definition_of_news_dedupe_helpers(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            js = f.read()
        self.assertEqual(js.count('function canonicalArticleUrl('), 1)
        self.assertEqual(js.count('function normalizedNewsTitle('), 1)

    def test_cleaned_snapshot_has_no_known_editorial_recommendation_rows(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        banned_fragments = [
            '每天固定喝一杯', '不想囤大量咖啡', '想喝便宜美式咖啡',
            '咖啡品項可以看', '都很適合連假和家人朋友一起買',
            '這週有兩種不同杯數的咖啡寄杯優惠', '這組優惠的優點是',
            '不用一次購買數十杯', '不過要注意', '星巴克也推出促銷', '每天固定喝一杯',
            '最便宜的是大杯美式',
        ]
        for item in snapshot['deals']:
            for fragment in banned_fragments:
                self.assertNotIn(fragment, item.get('offer', ''), item.get('offer', ''))

    def test_average_unit_price_does_not_override_combo_price_signature(self):
        a = '至 10/14 OKmart：大杯西西里咖啡單杯 39 元、2 杯 69 元，平均約 35 元／杯'
        b = '大杯西西里咖啡，單杯優惠價 39 元，一次買兩杯則是 69 元，平均一杯約 35 元'
        self.assertEqual(
            scraper._promotion_signature(scraper._normalise_offer_core(a)),
            scraper._promotion_signature(scraper._normalise_offer_core(b)),
        )
        out = scraper.deduplicate_deals([
            row('OKmart', a, '', '2026-10-14', 'https://news.example/sicilian-a'),
            row('OKmart', b, '', '', 'https://news.example/sicilian-b'),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]['source_urls']), 2)

    def test_snapshot_count_status_counts_and_dedup_are_consistent(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        self.assertEqual(snapshot['count'], len(snapshot['deals']))
        actual = {status: sum(1 for item in snapshot['deals'] if item.get('status') == status)
                  for status in ('active', 'upcoming', 'verify', 'expired')}
        self.assertEqual(snapshot['counts'], actual)
        self.assertEqual(len(scraper.deduplicate_deals(snapshot['deals'])), snapshot['count'])
        self.assertEqual(snapshot.get('processing_version'), 'v6.17')

    def test_frontend_title_is_version_neutral_and_pxmart_is_ordered(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            html = f.read()
        self.assertIn('<title>省咖啡｜優惠雷達</title>', html)
        self.assertNotIn('<title>省咖啡｜優惠雷達 v6.1</title>', html)
        self.assertGreaterEqual(html.count("'全聯'"), 3)
        self.assertIn("'全聯': 'brand-pxmart'", html)

    def test_frontend_is_pure_view_for_deals_json_and_has_brand_anchor_nav(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            js = f.read()
        self.assertIn("fetch('./deals.json?t=' + Date.now()", js)
        self.assertNotIn('dedupeDealRecords', js)
        self.assertNotIn('normalizeDealCore', js)
        self.assertNotIn('productIdentity', js)
        self.assertNotIn('promotionSignature', js)
        self.assertIn('renderBrandQuickLinks', js)
        self.assertIn('brandAnchorId', js)



    def test_yahoo_typhoon_snapshot_reassigns_exact_nine_cross_store_rows(self):
        url = scraper.URL_YAHOO_TYPHOON
        offers = [
            ('美廉社', '大杯濃萃美式買5送5，5折（原價50元、特價25元）'),
            ('美廉社', '大杯濃萃鮮奶拿鐵買5送5，5折（原價60元、特價30元）'),
            ('美廉社', '大杯美式買5送5，5折（原價45元、特價23元）'),
            ('美廉社', '大杯鮮奶拿鐵買5送5，5折（原價55元、特價28元）'),
            ('萊爾富', '燕麥拿鐵買1送1，5折（原價75元、特價38元）'),
            ('萊爾富', '特大杯特濃美式買1送1，5折（原價65元、特價33元）'),
            ('萊爾富', '特大杯美式買1送1，5折（原價60元、特價30元）'),
            ('萊爾富', '大杯特濃拿鐵買30送30，5折（原價65元、特價33元）'),
            ('萊爾富', '大杯特濃美式買30送30，5折（原價55元、特價28元）'),
        ]
        raw = [row('全家', offer, '2026-10-14', '2026-10-31', url, '颱風假咖啡優惠！萊爾富買一送一 7-11美式2杯66元') for _, offer in offers]
        out = scraper.deduplicate_deals(raw)
        self.assertEqual(len(out), 9)
        for expected_store, offer in offers:
            with self.subTest(offer=offer):
                found = [item for item in out if item['offer'] == offer]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]['store'], expected_store)

    def test_generic_thick_or_concentrated_product_name_does_not_guess_store(self):
        self.assertEqual(scraper.infer_store_from_product('大杯特濃美式買2送2'), '')
        self.assertEqual(scraper.infer_store_from_product('大杯濃萃美式買5送5'), '')
        self.assertEqual(scraper.infer_store_from_product('特大杯重乳拿鐵買1送1'), '萊爾富')

    def test_explicit_single_store_in_global_summary_updates_context_before_reset(self):
        article = {
            'title': '超商咖啡優惠整理',
            'url': 'https://news.example/context-order',
            'published': '2026-10-23',
        }
        fetched = {
            'ok': True, 'title': article['title'], 'final_url': article['url'],
            'published': article['published'],
            'lines': [
                '全家',
                '全家大杯特濃美式買2送2',
                '超商咖啡優惠！萊爾富本週活動整理',
                '燕麥拿鐵買1送1',
            ],
        }
        out = scraper.extract_article_deals(article, fetched)
        hilife = [item for item in out if '燕麥拿鐵買1送1' in item.get('offer', '')]
        self.assertEqual(len(hilife), 1)
        self.assertEqual(hilife[0]['store'], '萊爾富')

    def test_yahoo_typhoon_override_is_source_scoped(self):
        unrelated = row('全家', '大杯濃萃美式買5送5，5折（原價50元、特價25元）',
                        '2026-10-14', '2026-10-31', 'https://news.example/not-yahoo-typhoon')
        self.assertEqual(scraper._yahoo_typhoon_store_override(unrelated, unrelated['offer']), '')

    def test_okmart_sicilian_editorial_prefix_and_unknown_date_duplicate_merge(self):
        url = 'https://news.example/okmart-sicilian'
        data = [
            row('OKmart', '大杯西西里咖啡，單杯優惠價 39 元，一次買兩杯則是 69 元，平均一杯約 35 元',
                '', '2026-10-14', url, '2026 雙十國慶咖啡優惠懶人包'),
            row('OKmart', '咖啡品項可以看大杯西西里咖啡，單杯優惠價 39 元，一次買兩杯則是 69 元，平均一杯約 35 元',
                '', '', url, '2026 雙十國慶咖啡優惠懶人包'),
        ]
        out = scraper.deduplicate_deals(data)
        sicilian = [item for item in out if '西西里咖啡' in item.get('offer', '')]
        self.assertEqual(len(sicilian), 1)
        self.assertEqual(len(sicilian[0]['source_urls']), 1)
        self.assertNotIn('咖啡品項可以看', sicilian[0]['offer'])


    def test_cleaned_snapshot_has_no_nine_yahoo_typhoon_ghosts_under_family(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        typhoon = scraper.canonical_url(scraper.URL_YAHOO_TYPHOON)
        target_products = (
            r'濃萃美式', r'濃萃鮮奶拿鐵', r'美式', r'鮮奶拿鐵',
            r'燕麥拿鐵', r'特大杯特濃美式', r'特大杯美式', r'特濃拿鐵', r'特濃美式',
        )
        for item in snapshot['deals']:
            urls = [item.get('article_url', ''), *(item.get('source_urls') or [])]
            has_typhoon_source = typhoon in {scraper.canonical_url(u) for u in urls if u}
            if item.get('store') != '全家' or not has_typhoon_source:
                continue
            core = re.sub(r'\s+', '', scraper._normalise_offer_core(item.get('offer', '')))
            is_simplemart_ghost = '買5送5' in core and any(re.search(p, core) for p in target_products[:4])
            is_hilife_bogo_ghost = '買1送1' in core and any(re.search(p, core) for p in target_products[4:7])
            is_hilife_bulk_ghost = '買30送30' in core and any(re.search(p, core) for p in target_products[7:9])
            self.assertFalse(is_simplemart_ghost or is_hilife_bogo_ghost or is_hilife_bulk_ghost, item['offer'])

        for expected in [
            '大杯濃萃美式買5送5', '大杯濃萃鮮奶拿鐵買5送5',
            '大杯美式買5送5', '大杯鮮奶拿鐵買5送5',
        ]:
            self.assertTrue(any(d.get('store') == '美廉社' and expected in d.get('offer', '') and
                                typhoon in {scraper.canonical_url(u) for u in [d.get('article_url', ''), *(d.get('source_urls') or [])] if u}
                                for d in snapshot['deals']), expected)
        self.assertTrue(any(d.get('store') == '萊爾富' and '大杯燕麥奶拿鐵' in d.get('offer', '') and re.search(r'買\s*[一1]\s*送\s*[一1]', d.get('offer', ''))
                            and typhoon in {scraper.canonical_url(u) for u in [d.get('article_url', ''), *(d.get('source_urls') or [])] if u}
                            for d in snapshot['deals']))
        self.assertTrue(any(d.get('store') == '萊爾富' and all(term in d.get('offer', '') for term in ('特大特濃美式', '特大重乳拿鐵', '大杯燕麥奶拿鐵')) and re.search(r'買\s*[一1]\s*送\s*[一1]', d.get('offer', ''))
                            and typhoon in {scraper.canonical_url(u) for u in [d.get('article_url', ''), *(d.get('source_urls') or [])] if u}
                            for d in snapshot['deals']))
        self.assertTrue(any(d.get('store') == '萊爾富' and '同品項買30送30' in d.get('offer', '')
                            and typhoon in {scraper.canonical_url(u) for u in [d.get('article_url', ''), *(d.get('source_urls') or [])] if u}
                            for d in snapshot['deals']))
        hilife_thirty = [d for d in snapshot['deals'] if d.get('store') == '萊爾富'
                         and '買30送30' in re.sub(r'\s+', '', d.get('offer', ''))
                         and '特濃' in d.get('offer', '')
                         and typhoon in {scraper.canonical_url(u) for u in [d.get('article_url', ''), *(d.get('source_urls') or [])] if u}]
        self.assertEqual(len(hilife_thirty), 1, [d.get('offer') for d in hilife_thirty])

    def test_okmart_sicilian_duplicate_variants_merge_even_when_one_date_is_missing(self):
        url = 'https://news.example/okmart-sicilian'
        data = [
            row('OKmart', '大杯西西里咖啡，單杯優惠價 39 元，一次買兩杯則是 69 元，平均一杯約 35 元',
                '', '2026-10-14', url, '2026 雙十國慶咖啡優惠懶人包'),
            row('OKmart', '咖啡品項可以看大杯西西里咖啡，單杯優惠價 39 元，一次買兩杯則是 69 元，平均一杯約 35 元',
                '', '', url, '2026 雙十國慶咖啡優惠懶人包'),
        ]
        records = [d for d in scraper.deduplicate_deals(data) if d.get('store') == 'OKmart' and '大杯西西里咖啡' in d.get('offer', '')]
        self.assertEqual(len(records), 1)
        self.assertIn('39 元', records[0]['offer'])
        self.assertIn('69 元', records[0]['offer'])


    def test_frontend_supports_chinese_english_and_thai_language_switch(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            page = f.read()
        self.assertIn('<select id="language-select"', page)
        self.assertIn('<option value="zh-Hant">中文</option>', page)
        self.assertIn('<option value="en">English</option>', page)
        self.assertIn('<option value="th">ไทย</option>', page)
        self.assertIn("localStorage.getItem('coffee-deals-language')", page)
        self.assertIn("localStorage.setItem('coffee-deals-language', currentLang)", page)
        self.assertIn("document.documentElement.lang = htmlLangs[currentLang]", page)
        self.assertIn('Coffee Deals Available Today', page)
        self.assertIn('โปรกาแฟที่ใช้ได้วันนี้', page)

    def test_frontend_translates_offer_presentation_and_keeps_original_outside_link(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            page = f.read()
        self.assertIn('function localizeText(value, lang = currentLang)', page)
        self.assertIn('function formatDealDateRange(deal)', page)
        self.assertIn("function makeOriginalText(original, type = 'offer')", page)
        self.assertIn('entry.appendChild(card);', page)
        self.assertIn('if (originalNode) entry.appendChild(originalNode);', page)
        self.assertNotIn('appendOriginalText(', page)
        self.assertIn('English/Thai offer text is a helpful translation', page)

    def test_frontend_does_not_nest_original_text_details_inside_anchor(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            page = f.read()
        self.assertIn('.deal-entry>.original-copy', page)
        self.assertNotIn("appendOriginalText(a, d.title, 'headline')", page)
        self.assertIn('News headlines remain in the publisher’s original language', page)



    def test_starbucks_weekly_offers_are_curated_from_official_source(self):
        deals = scraper.curated_deals()
        starbucks = [d for d in deals if d.get('store') == '星巴克' and d.get('article_url') == scraper.URL_STARBUCKS_UNIOPEN]
        self.assertEqual(len(starbucks), 2)
        monday = next(d for d in starbucks if '每週一' in d.get('schedule_note', ''))
        tuesday = next(d for d in starbucks if '每週二' in d.get('schedule_note', ''))
        self.assertEqual((monday['start_date'], monday['end_date']), ('2026-07-01', '2026-12-31'))
        self.assertIn('買 1 送 1', monday['offer'])
        self.assertIn('uniopen', monday['offer'].lower())
        self.assertLessEqual(len(monday['offer']), 45)
        self.assertIn('第二杯由星巴克招待', monday['details'])
        self.assertIn('買二送二', monday['details'])
        self.assertIn('限當場領取', monday['details'])
        self.assertLessEqual(len(tuesday['offer']), 45)
        self.assertIn('164 元', tuesday['details'])
        self.assertIn('188 元', tuesday['details'])
        self.assertFalse(monday['needs_check'])
        self.assertFalse(tuesday['needs_check'])

    def test_starbucks_legacy_weekly_summaries_consolidate_to_two_official_cards(self):
        old = [
            row('星巴克', '星巴克買1送1一次看', '2026-10-19', '2026-10-25', 'https://applealmond.com/posts/329295'),
            row('星巴克', '活動期間至 2026 年 12 月 31 日，每週一使用中國信託 uniopen 聯名卡，於星巴克實體門市購買 2 杯大杯（含）以上、容量、冰熱與口味皆相同的指定飲料，其中一杯由星巴克招待，每人每次最多可享買 2 送 2', '', '2026-12-31', 'https://applealmond.com/posts/329295'),
            row('星巴克', '星巴克咖啡優惠：10/19 週一買一送一', '', '', 'https://applealmond.com/posts/329295'),
            row('星巴克', '週一好友分享日星巴克大杯飲料免費多一杯', '', '', 'https://www.cosmopolitan.com/tw/lifestyle/hot-topics/g74211453/hilife-coffee-1022'),
            row('星巴克', '10/20 星巴克週二飲料＋糕點 8 折', '', '', 'https://applealmond.com/posts/329295'),
            row('星巴克', '大杯美式咖啡＋起司里肌可頌：164 元', '', '', 'https://applealmond.com/posts/329295'),
            row('星巴克', '大杯美式咖啡＋經典起司蛋糕：188 元', '', '', 'https://applealmond.com/posts/329295'),
        ]
        out = scraper.deduplicate_deals(old + scraper.curated_deals())
        weekly = [d for d in out if d.get('store') == '星巴克' and d.get('article_url') == scraper.URL_STARBUCKS_UNIOPEN]
        self.assertEqual(len(weekly), 2)
        monday = next(d for d in weekly if '每週一' in d.get('schedule_note', '') or '每週一' in d.get('offer', ''))
        tuesday = next(d for d in weekly if '每週二' in d.get('schedule_note', '') or '每週二' in d.get('offer', ''))
        self.assertIn('買 1 送 1', monday['offer'])
        self.assertIn('188 元', tuesday.get('details', ''))
        self.assertIn('https://applealmond.com/posts/329295', monday['source_urls'])
        self.assertIn('https://www.cosmopolitan.com/tw/lifestyle/hot-topics/g74211453/hilife-coffee-1022', monday['source_urls'])
        self.assertFalse(any(d.get('offer') == '星巴克買1送1一次看' for d in out))
        self.assertFalse(any('起司里肌可頌：164 元' == d.get('offer') for d in out))

    def test_offer_priority_orders_single_one_plus_one_then_two_plus_two_and_bigger_bundles(self):
        offers = [
            '大杯美式 17 杯組 500 元',
            '大杯美式買2送2',
            '大杯美式單杯 39 元',
            '大杯美式買1送1',
            '大杯美式 2 杯 69 元',
            '大杯美式買5送5',
            '大杯美式買2送1',
            '大杯美式 兩杯 69 元',
            '大杯美式平均一杯約 28 元',
            '大杯美式 100 杯組 2,800 元',
        ]
        actual = sorted(offers, key=scraper.offer_priority_weight)
        self.assertEqual(actual[:7], [
            '大杯美式單杯 39 元',
            '大杯美式買1送1',
            '大杯美式 2 杯 69 元',
            '大杯美式 兩杯 69 元',
            '大杯美式買2送1',
            '大杯美式買2送2',
            '大杯美式買5送5',
        ])
        self.assertGreater(scraper.offer_priority_weight('大杯美式平均一杯約 28 元')[0], 10)
        self.assertEqual(scraper._count_token('三十'), 30)
        self.assertEqual(scraper._count_token('一百'), 100)

    def test_starbucks_monday_bogo_is_hero_before_starquench_and_tuesday_combo(self):
        rows = [
            row('7-ELEVEN', '大杯美式買1送1', '2026-10-20', '2026-10-31', 'https://news.example/711'),
            row('星巴克', '星巴克買2送2', '2026-10-20', '2026-12-31', 'https://news.example/star-2'),
            row('星巴克', '星沁爽特大杯單一價99元', '2026-09-09', '2026-11-03', 'https://news.example/star-1'),
            row('星巴克', '每週二｜uniopen 聯名卡指定飲料＋糕點 8 折', '2026-07-01', '2026-12-31', 'https://news.example/star-tue'),
            row('星巴克', '每週一 11:00–20:00｜uniopen 聯名卡買 1 送 1', '2026-07-01', '2026-12-31', 'https://news.example/star-mon'),
        ]
        actual = sorted(rows, key=scraper.deal_sort_key)
        self.assertEqual(actual[0]['offer'], '每週一 11:00–20:00｜uniopen 聯名卡買 1 送 1')
        self.assertIn('星沁爽', actual[1]['offer'])
        self.assertIn('每週二', actual[2]['offer'])
        self.assertIn('買2送2', actual[3]['offer'])
        self.assertEqual(actual[4]['store'], '7-ELEVEN')

    def test_average_unit_price_never_counts_as_single_cup_price(self):
        for offer in [
            '大杯美式平均一杯 22.5 元',
            '單杯平均 35 元，換算後約 5 折',
            '大杯特濃美式每杯約 28 元，長期寄杯更划算',
        ]:
            with self.subTest(offer=offer):
                self.assertGreater(scraper.offer_priority_weight(offer)[0], 10)

    def test_frontend_deal_rendering_uses_backend_order_without_duplicate_offer_sorter(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            page = f.read()
        self.assertIn("const STORE_DISPLAY_ORDER = ['星巴克','7-ELEVEN'", page)
        self.assertNotIn('function offerPriorityKey(value)', page)
        self.assertNotIn('function compareDealsByStoreAndOffer(a, b)', page)
        self.assertNotIn('active.sort(compareDealsByStoreAndOffer)', page)
        self.assertIn('SSOT：所有優惠排序由 scraper.py 寫入 deals.json', page)
        self.assertIn("if (d.details) card.appendChild(makeEl('div', 'deal-details', localizeText(d.details)))", page)

    def test_v611_snapshot_places_starbucks_monday_bogo_first_and_uses_short_copy(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        self.assertEqual(snapshot['count'], len(snapshot['deals']))
        self.assertEqual(snapshot['deals'][0]['store'], '星巴克')
        self.assertIn('每週一', snapshot['deals'][0].get('schedule_note', '') + snapshot['deals'][0].get('offer', ''))
        self.assertIn('uniopen', snapshot['deals'][0]['offer'].lower())
        self.assertIn('買 1 送 1', snapshot['deals'][0]['offer'])
        starbucks = [d for d in snapshot['deals'] if d.get('store') == '星巴克' and d.get('status') == 'active']
        self.assertTrue(scraper.is_starbucks_monday_hero(starbucks[0]))
        monday = starbucks[0]
        self.assertLessEqual(len(monday['offer']), 45)
        self.assertIn('uniopen', monday['offer'].lower())
        self.assertIn('第二杯由星巴克招待', monday.get('details', ''))
        self.assertEqual(snapshot.get('processing_version'), 'v6.17')
        self.assertEqual(len(scraper.deduplicate_deals(snapshot['deals'])), snapshot['count'])


    def test_official_starbucks_allowlist_checks_source_urls_when_article_url_changes(self):
        item = row(
            '星巴克',
            '每週一 11:00–20:00｜uniopen 聯名卡買 1 送 1',
            '2026-07-01', '2026-12-31',
            'https://applealmond.com/posts/329295',
        )
        item['source_urls'] = [
            item['article_url'],
            scraper.URL_STARBUCKS_UNIOPEN + '&utm_source=test',
        ]
        item['details'] = '官方說明：第二杯由星巴克招待。'
        self.assertFalse(scraper.is_non_offer_record(item))
        cleaned = scraper.deduplicate_deals([item])
        self.assertEqual(len(cleaned), 1)
        self.assertIn('買 1 送 1', cleaned[0]['offer'])
        self.assertIn(scraper.canonical_url(scraper.URL_STARBUCKS_UNIOPEN), cleaned[0]['source_urls'])
        self.assertIn('第二杯由星巴克招待', cleaned[0]['details'])

    def test_details_are_present_by_default_and_preserved_while_deduplicating(self):
        base = scraper.make_deal(
            '7-ELEVEN', '大杯美式 2 杯 66 元', 'https://news.example/details-a',
            '優惠 A', '2026-10-20', '2026-10-31', '', '2026-10-20',
        )
        self.assertEqual(base.get('details'), '')
        a = row('7-ELEVEN', '大杯美式 2 杯 66 元', '2026-10-20', '2026-10-31', 'https://news.example/details-a')
        b = row('7-ELEVEN', '大杯美式 2 杯 66 元', '2026-10-20', '2026-10-31', 'https://news.example/details-b')
        a['details'] = '官方活動說明：限指定門市。'
        b['details'] = '補充說明：每人每次限購一組。'
        out = scraper.deduplicate_deals([a, b])
        self.assertEqual(len(out), 1)
        self.assertIn('官方活動說明：限指定門市。', out[0]['details'])
        self.assertIn('補充說明：每人每次限購一組。', out[0]['details'])

    def test_average_price_sentence_with_real_six_cup_offer_sorts_as_six_cups(self):
        editorial = '特濃美式平均一杯約 28 元，單杯價格接近大量寄杯，但一次買 6 杯 230 元'
        actual_offer = '特濃美式 6 杯 230 元'
        self.assertEqual(scraper.offer_priority_weight(editorial)[0], 6)
        self.assertNotEqual(scraper.offer_priority_weight(editorial)[0], 1)
        ordered = sorted([editorial, actual_offer], key=scraper.offer_priority_weight)
        self.assertEqual(ordered[0], actual_offer)
        self.assertEqual(scraper.offer_priority_weight(actual_offer)[0], 6)

    def test_chinese_two_cup_bundle_precedes_buy_two_send_two_four_cups(self):
        offers = ['大杯美式買 2 送 2（共 4 杯）', '大杯美式兩杯 66 元']
        ordered = sorted(offers, key=scraper.offer_priority_weight)
        self.assertEqual(ordered[0], '大杯美式兩杯 66 元')
        self.assertEqual(ordered[1], '大杯美式買 2 送 2（共 4 杯）')


    def test_exact_normalized_offer_text_is_compatible_even_without_product_tokens(self):
        offer = '每週一 11:00–20:00｜uniopen 聯名卡買 1 送 1'
        self.assertTrue(scraper._products_compatible(offer, offer))
        products, _ = scraper._product_identity(offer)
        self.assertFalse(products)

    def test_starbucks_official_weekly_cards_consolidate_all_duplicates_and_legacy_rows(self):
        official = scraper.URL_STARBUCKS_UNIOPEN
        monday_offer = '每週一 11:00–20:00｜uniopen 聯名卡買 1 送 1'
        tuesday_offer = '每週二｜uniopen 聯名卡指定飲料＋糕點 8 折'
        monday_a = row('星巴克', monday_offer, '2026-07-01', '2026-12-31', official)
        monday_a['source_urls'] = [official, 'https://news.example/monday-a']
        monday_a['details'] = '大杯以上相同飲料，第二杯由星巴克招待。'
        monday_b = row('星巴克', monday_offer, '2026-07-01', '2026-12-31', official)
        monday_b['source_urls'] = [official, 'https://news.example/monday-b']
        monday_b['details'] = '每次最多買二送二，限當場領取。'
        tuesday_a = row('星巴克', tuesday_offer, '2026-07-01', '2026-12-31', official)
        tuesday_a['source_urls'] = [official, 'https://news.example/tuesday-a']
        tuesday_b = row('星巴克', tuesday_offer, '2026-07-01', '2026-12-31', official)
        tuesday_b['source_urls'] = [official, 'https://news.example/tuesday-b']
        legacy_monday = row('星巴克', '「星巴克買1送1」10/26快閃1天', '2026-10-26', '2026-10-26', 'https://news.example/monday-legacy')
        legacy_tuesday = row('星巴克', '大杯美式咖啡＋起司里肌可頌：164 元', '', '', 'https://news.example/tuesday-legacy')

        out = scraper.deduplicate_deals([monday_a, monday_b, tuesday_a, tuesday_b, legacy_monday, legacy_tuesday])
        weekly = [d for d in out if d.get('store') == '星巴克' and scraper._has_official_starbucks_source(d)]
        self.assertEqual(len(weekly), 2)
        monday = next(d for d in weekly if '每週一' in d.get('schedule_note', '') or '每週一' in d.get('offer', ''))
        tuesday = next(d for d in weekly if '每週二' in d.get('schedule_note', '') or '每週二' in d.get('offer', ''))
        self.assertEqual(monday['article_url'], scraper.canonical_url(official))
        self.assertEqual((monday['start_date'], monday['end_date']), ('2026-07-01', '2026-12-31'))
        self.assertIn('https://news.example/monday-a', monday['source_urls'])
        self.assertIn('https://news.example/monday-b', monday['source_urls'])
        self.assertIn('https://news.example/monday-legacy', monday['source_urls'])
        self.assertIn('大杯以上相同飲料', monday['details'])
        self.assertIn('每次最多買二送二', monday['details'])
        self.assertIn('https://news.example/tuesday-a', tuesday['source_urls'])
        self.assertIn('https://news.example/tuesday-b', tuesday['source_urls'])
        self.assertIn('https://news.example/tuesday-legacy', tuesday['source_urls'])

    def test_generic_and_specific_711_line_gift_bogo_merge_only_when_source_is_shared(self):
        source = 'https://applealmond.com/posts/329295'
        generic = row('7-ELEVEN', '7-ELEVEN LINE 禮物指定咖啡買一送一', '2026-10-14', '2026-10-27', source)
        generic['source_urls'] = [source, 'https://www.nownews.com/news/6884698']
        specific = row('7-ELEVEN', '7-ELEVEN LINE 禮物：指定特選美式、拿鐵電子票券買一送一', '', '', source)
        out = scraper.deduplicate_deals([generic, specific])
        matches = [d for d in out if 'LINE 禮物' in d.get('offer', '')]
        self.assertEqual(len(matches), 1)
        self.assertIn('特選美式', matches[0]['offer'])
        self.assertEqual((matches[0]['start_date'], matches[0]['end_date']), ('2026-10-14', '2026-10-27'))
        self.assertIn('https://www.nownews.com/news/6884698', matches[0]['source_urls'])

    def test_generic_family_cafe_bogo_can_merge_to_specific_same_source_combo(self):
        source = 'https://news.example/family-campaign'
        generic = row('全家', '全家特濃咖啡買 2 送 2', '2026-10-23', '2026-10-27', source)
        specific = row('全家', "Let's Cafe 大杯特濃美式／拿鐵同品項買 2 送 2", '2026-10-23', '2026-10-27', source)
        out = scraper.deduplicate_deals([generic, specific])
        matches = [d for d in out if '買 2 送 2' in d.get('offer', '') or '買2送2' in d.get('offer', '')]
        self.assertEqual(len(matches), 1)
        self.assertIn('美式', matches[0]['offer'])
        self.assertIn('拿鐵', matches[0]['offer'])

    def test_multi_offer_news_summary_headline_is_filtered(self):
        headline = '7-11本週咖啡優惠「11款咖啡、茶飲優惠組合」10/22快閃10天，最高現省500元！'
        self.assertTrue(scraper.is_non_offer_record({'store': '7-ELEVEN', 'offer': headline}))
        self.assertEqual(scraper.deduplicate_deals([
            row('7-ELEVEN', headline, '', '', 'https://news.example/summary')
        ]), [])

    def test_v611_snapshot_has_one_starbucks_weekly_card_each_and_no_summary_headline(self):
        import json
        with open(os.path.join(HERE, 'deals.json'), encoding='utf-8') as f:
            snapshot = json.load(f)
        deals = snapshot['deals']
        monday = [d for d in deals if d.get('store') == '星巴克' and ('每週一' in d.get('schedule_note', '') or '每週一' in d.get('offer', '')) and 'uniopen' in d.get('offer', '').lower()]
        tuesday = [d for d in deals if d.get('store') == '星巴克' and ('每週二' in d.get('schedule_note', '') or '每週二' in d.get('offer', '')) and 'uniopen' in d.get('offer', '').lower()]
        line_gift = [d for d in deals if d.get('store') == '7-ELEVEN' and 'LINE 禮物' in d.get('offer', '') and ('買一送一' in d.get('offer', '') or '買 1 送 1' in d.get('offer', ''))]
        self.assertEqual(len(monday), 1)
        self.assertEqual(len(tuesday), 1)
        self.assertEqual(len(line_gift), 1)
        self.assertFalse(any('11款咖啡' in d.get('offer', '') for d in deals))
        self.assertEqual(len(scraper.deduplicate_deals(deals)), len(deals))


    def test_v611_hilife_happy_hour_is_separated_from_calendar_range(self):
        source = 'https://tw.news.yahoo.com/4%E5%A4%A7%E8%B6%85%E5%95%86.html'
        raw = row('萊爾富', '大杯美式/大杯拿鐵單杯29元', '2026-10-14', '2026-11-10', source)
        raw['date_text'] = '10/14～11/10；每週六日 10:00～14:00'
        out = scraper.deduplicate_deals([raw])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['date_text'], '10/14～11/10')
        self.assertIn('每週六', out[0]['schedule_note'])
        self.assertIn('10:00', out[0]['schedule_note'])
        self.assertIn('Happy Hour', out[0]['schedule_note'])

    def test_v611_schedule_context_is_attached_to_only_the_next_offer(self):
        lines = [
            '萊爾富 Happy Hour！10月14日至11月10日每週六日10:00至14:00',
            '大杯美式/大杯拿鐵單杯29元',
            'Hi-Life VIP APP 整買零取買10送10',
        ]
        fetched = {'ok': True, 'title': '萊爾富咖啡優惠', 'final_url': 'https://news.example/hilife',
                   'published': '2026-10-22', 'lines': lines}
        deals = scraper.extract_article_deals({'title': fetched['title'], 'url': fetched['final_url']}, fetched)
        target = next((d for d in deals if '29元' in d['offer']), None)
        bulk = next((d for d in deals if '買10送10' in d['offer'] or '買 10 送 10' in d['offer']), None)
        self.assertIsNotNone(target)
        self.assertIsNotNone(bulk)
        self.assertIn('每週六', target.get('schedule_note', ''))
        self.assertEqual(bulk.get('schedule_note', ''), '')

    def test_v611_schedule_context_resets_on_store_change_and_global_summary(self):
        lines = [
            '萊爾富 Happy Hour 每週六日10:00至14:00',
            '大杯美式單杯29元',
            '四大超商優惠一次看',
            '全家大單品咖啡同品項加10元多1杯',
        ]
        fetched = {'ok': True, 'title': '咖啡優惠', 'final_url': 'https://news.example/multi',
                   'published': '2026-10-22', 'lines': lines}
        deals = scraper.extract_article_deals({'title': fetched['title'], 'url': fetched['final_url']}, fetched)
        family = next((d for d in deals if d.get('store') == '全家'), None)
        self.assertIsNotNone(family)
        self.assertEqual(family.get('schedule_note', ''), '')

    def test_v611_schedule_context_resets_on_additional_transition(self):
        lines = [
            '萊爾富 Happy Hour 每週六日10:00至14:00',
            '大杯美式單杯29元',
            '另外還有萊爾富 APP 整買零取買10送10',
        ]
        fetched = {'ok': True, 'title': '萊爾富咖啡優惠', 'final_url': 'https://news.example/transition',
                   'published': '2026-10-22', 'lines': lines}
        deals = scraper.extract_article_deals({'title': fetched['title'], 'url': fetched['final_url']}, fetched)
        target = next((d for d in deals if '29元' in d['offer']), None)
        bulk = next((d for d in deals if '買10送10' in d['offer'] or '買 10 送 10' in d['offer']), None)
        self.assertIsNotNone(target)
        self.assertIsNotNone(bulk)
        self.assertTrue(target.get('schedule_note'))
        self.assertEqual(bulk.get('schedule_note', ''), '')

    def test_v611_make_deal_has_schedule_note_and_weekly_curated_notes(self):
        curated = scraper.curated_deals()
        monday = next(d for d in curated if d.get('store') == '星巴克' and '買 1 送 1' in d.get('offer', ''))
        tuesday = next(d for d in curated if d.get('store') == '星巴克' and '8 折' in d.get('offer', ''))
        showba = next(d for d in curated if d.get('store') == '小北百貨' and '買 1 送 1' in d.get('offer', '') and '會員日' in d.get('schedule_note', ''))
        self.assertEqual(monday.get('schedule_note'), '每週一 11:00–20:00')
        self.assertEqual(tuesday.get('schedule_note'), '每週二')
        self.assertEqual(showba.get('schedule_note'), '每週三｜會員日')
        self.assertIn('schedule_note', scraper.make_deal('萊爾富', '單杯29元', 'https://news.example', 'test'))

    def test_v611_old_snapshot_fallback_can_extract_schedule_from_date_text(self):
        old = row('萊爾富', '大杯美式／大杯拿鐵單杯29元', '2026-10-14', '2026-11-10', 'https://news.example/old')
        old.pop('schedule_note', None)
        old['date_text'] = '10/14～11/10；每週六日 10:00～14:00'
        normalized = scraper._normalize_schedule_fields(old)
        self.assertEqual(normalized['date_text'], '10/14～11/10')
        self.assertTrue(normalized['schedule_note'])

    def test_v611_safe_write_outputs_single_valid_json_document(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'deals.json')
        payload = {'processing_version': 'v6.11', 'count': 1, 'deals': [{'offer': '單杯29元'}]}
        scraper.safe_write(payload, path)
        with open(path, encoding='utf-8') as f:
            loaded = json.load(f)
        self.assertEqual(loaded, payload)




class ListingDiscoveryRegressionTests(unittest.TestCase):
    def test_nownews_listing_discovers_new_article_ids_by_offer_title(self):
        html = """
        <html><body>
          <article><h2><a href="/news/6886549">星巴克買一送一咖啡優惠、85度C第二杯4折</a></h2></article>
          <article><h2><a href="/news/6880001">政治人物談話與國際新聞</a></h2></article>
        </body></html>
        """
        found = scraper.extract_listing_candidates(
            html, 'https://www.nownews.com/cat/lifestyle/', 'nownews', limit=10
        )
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]['url'].endswith('/news/6886549'))
        self.assertIn('85度C', found[0]['title'])

    def test_85c_official_news_listing_discovers_promotion_article(self):
        html = """
        <html><body>
          <a href="/News_content.php?data=9989">85度C 萬聖節咖啡優惠 第二杯4折</a>
          <a href="/News_content.php?data=9990">企業介紹與品牌故事</a>
        </body></html>
        """
        found = scraper.extract_listing_candidates(
            html, 'https://www.85cafe.com/News.php', '85c', limit=10
        )
        self.assertEqual(len(found), 1)
        self.assertIn('data=9989', found[0]['url'])

    def test_curated_current_offers_have_separate_channel_labels_and_end_dates(self):
        items = scraper.curated_deals()
        selected = [x for x in items if x.get('article_url', '').endswith('/news/6884695')]
        offers = [x['offer'] for x in selected]
        self.assertTrue(any('Uber Eats' in offer and '買 1 送 1' in offer for offer in offers))
        self.assertTrue(any('磚壓套餐限時 6 折' in offer for offer in offers))
        self.assertTrue(any('門市限定' in offer and '芒果綠茶' in offer for offer in offers))
        self.assertTrue(all(x['end_date'] == '2026-10-31' for x in selected))
        deduped = scraper.deduplicate_deals(selected)
        self.assertEqual(len(deduped), 3)
        scopes = {scraper._deal_channel_scope(x) for x in deduped}
        self.assertEqual(scopes, {'delivery', 'store'})

if __name__ == '__main__':
    unittest.main(verbosity=2)


class DynamicDiscoveryV613Tests(unittest.TestCase):
    def test_source_discovery_runs_each_publisher_query_and_isolates_failure(self):
        original = scraper.rss
        calls = []
        def fake_rss(query):
            calls.append(query)
            if "applealmond" in query:
                raise RuntimeError("simulated source outage")
            return [{
                "title": "新咖啡優惠文章",
                "url": "https://news.google.com/rss/articles/ARTICLE-" + str(len(calls)),
                "published": "Fri, 06 Nov 2026 08:00:00 GMT",
            }]
        scraper.rss = fake_rss
        try:
            articles, stats = scraper.discover_source_rss_articles()
        finally:
            scraper.rss = original
        self.assertEqual(len(calls), sum(len(v) for v in scraper.SOURCE_DISCOVERY_QUERIES.values()))
        self.assertEqual(len(stats), len(scraper.SOURCE_DISCOVERY_QUERIES))
        self.assertFalse(stats["蘋果仁"]["ok"])
        self.assertTrue(stats["NOWnews"]["ok"])
        self.assertGreater(len(articles), 0)

    def test_source_discovery_deduplicates_same_article_within_source(self):
        original = scraper.rss
        queries = scraper.SOURCE_DISCOVERY_QUERIES
        scraper.SOURCE_DISCOVERY_QUERIES = {"測試來源": ["q1", "q2"]}
        def fake_rss(query):
            return [{"title": "同一篇文章", "url": "https://news.google.com/rss/articles/SAME", "published": ""}]
        scraper.rss = fake_rss
        try:
            articles, stats = scraper.discover_source_rss_articles()
        finally:
            scraper.rss = original
            scraper.SOURCE_DISCOVERY_QUERIES = queries
        self.assertEqual(len(articles), 1)
        self.assertEqual(stats["測試來源"]["discovered"], 1)

    def test_dynamic_listing_candidate_filtering_keeps_only_valid_nownews_article_paths(self):
        html = """
        <article><h2><a href="/news/6999999">最新咖啡優惠 買一送一</a></h2></article>
        <a href="/news/6999998">一般政治新聞</a>
        <a href="https://example.com/news/123">咖啡優惠</a>
        """
        found = scraper.extract_listing_candidates(html, "https://www.nownews.com/cat/lifestyle/", "nownews")
        self.assertEqual(len(found), 1)
        self.assertIn("/news/6999999", found[0]["url"])

    def test_expired_october_deals_are_not_active_on_november_six(self):
        expired = {"start_date": "2026-10-19", "end_date": "2026-10-31"}
        old_today = scraper.TODAY
        try:
            scraper.TODAY = __import__("datetime").date(2026, 11, 6)
            self.assertEqual(scraper.infer_status(expired["start_date"], expired["end_date"]), "expired")
        finally:
            scraper.TODAY = old_today


class PXMartV614Tests(unittest.TestCase):
    def test_pxmart_source_discovery_query_is_registered(self):
        self.assertIn("全聯", scraper.SOURCE_DISCOVERY_QUERIES)
        self.assertTrue(any("pxmart.com.tw" in q and "pxbox.pxmart.com.tw" in q for q in scraper.SOURCE_DISCOVERY_QUERIES["全聯"]))

    def test_batch_pickup_is_detected_as_online_channel(self):
        self.assertIsNotNone(scraper.SCHEDULE_CHANNEL_SWITCH_RE.search("PXGo 分批取"))

    def test_curated_pxmart_eco_cup_is_five_dollars_not_historical_eight(self):
        px = [d for d in scraper.curated_deals() if d.get("store") == "全聯"]
        eco = next(d for d in px if "自備環保杯" in d.get("offer", ""))
        self.assertIn("現折 5 元", eco["offer"])
        self.assertEqual(eco["status"], "verify")  # 官方頁未提供截止日，不偽造有效期限
        self.assertFalse(eco["needs_check"])

    def test_pxmart_eco_cup_record_passes_non_offer_filter(self):
        eco = next(
            d for d in scraper.curated_deals()
            if d.get("store") == "全聯" and "自備環保杯" in d.get("offer", "")
        )
        self.assertFalse(scraper.is_non_offer_record(eco))

    def test_pxmart_eco_cup_survives_full_deduplication_pipeline(self):
        curated = scraper.curated_deals()
        out = scraper.deduplicate_deals(curated)
        eco = [
            d for d in out
            if d.get("store") == "全聯" and "自備環保杯" in d.get("offer", "")
        ]
        self.assertEqual(len(eco), 1)
        self.assertEqual(eco[0]["status"], "verify")
        self.assertIn("現折 5 元", eco[0]["offer"])

    def test_v615_snapshot_contains_pxmart_eco_cup_verify_card_and_consistent_counts(self):
        with open(os.path.join(HERE, "deals.json"), encoding="utf-8") as f:
            snapshot = json.load(f)
        self.assertEqual(snapshot.get("processing_version"), "v6.17")
        cards = [
            d for d in snapshot.get("deals", [])
            if d.get("store") == "全聯" and "自備環保杯" in d.get("offer", "")
        ]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["status"], "verify")
        self.assertEqual(cards[0]["start_date"], "")
        self.assertEqual(cards[0]["end_date"], "")
        self.assertEqual(snapshot["count"], len(snapshot["deals"]))
        counts = {key: sum(1 for d in snapshot["deals"] if d.get("status") == key)
                  for key in ("active", "upcoming", "verify", "expired")}
        self.assertEqual(snapshot["counts"], counts)

    def test_pxmart_october_batch_pickup_offers_are_expired(self):
        px = [d for d in scraper.curated_deals() if d.get("store") == "全聯"]
        batch = [d for d in px if "分批取" in d.get("offer", "")]
        self.assertEqual(len(batch), 2)
        self.assertTrue(all(d["status"] == "expired" for d in batch))
        self.assertTrue(any("9 杯 199 元" in d["offer"] for d in batch))
        self.assertTrue(any("6 杯 199 元" in d["offer"] for d in batch))

    def test_frontend_has_pxmart_portal_and_v614_version(self):
        with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
            html = f.read()
        self.assertIn('content="v6.17"', html)
        self.assertIn('href="https://pxbox.pxmart.com.tw/"', html)
        self.assertIn("'portal-12':'全聯福利中心|PX Pay 分批取'", html)
        self.assertIn("'portal-12':'PX Mart|PX Pay Bundles'", html)
        self.assertIn("'portal-12':'PX Mart|แพ็กแก้ว PX Pay'", html)


class V616DiscoveryAndArticleRegressionTests(unittest.TestCase):
    """回歸測試：使用者提供的 3 篇 NOWnews + 1 篇 Yahoo 雙11文章。"""

    def setUp(self):
        self._old_today = scraper.TODAY
        from datetime import date
        scraper.TODAY = date(2026, 11, 6)

    def tearDown(self):
        scraper.TODAY = self._old_today

    def _extract(self, title, url, published, lines):
        article = {"title": title, "url": url, "published": published}
        fetched = {
            "ok": True,
            "title": title,
            "final_url": url,
            "published": published,
            "lines": lines,
        }
        return scraper.deduplicate_deals(scraper.extract_article_deals(article, fetched))

    def test_all_four_user_supplied_articles_are_seeded(self):
        urls = {x["url"] for x in scraper.SEED_ARTICLES}
        self.assertTrue({
            "https://www.nownews.com/news/6889517",
            "https://www.nownews.com/news/6889553",
            "https://www.nownews.com/news/6888826",
            scraper.URL_YAHOO_DOUBLE11,
        }.issubset(urls))

    def test_rss_queries_are_not_tied_to_a_stale_month(self):
        combined = " ".join(scraper.RSS_QUERIES + [q for qs in scraper.SOURCE_DISCOVERY_QUERIES.values() for q in qs])
        self.assertNotIn("2026 10月 11月", combined)
        self.assertIn("OKmart", scraper.SOURCE_DISCOVERY_QUERIES)
        self.assertIn("7-ELEVEN", scraper.SOURCE_DISCOVERY_QUERIES)
        self.assertIn("全家", scraper.SOURCE_DISCOVERY_QUERIES)

    def test_recent_articles_are_prioritized_before_fetch_limit(self):
        articles = [
            {"url": "https://example.com/old", "published": "2026-10-01"},
            {"url": "https://example.com/new", "published": "2026-11-05T19:15:00+08:00"},
            {"url": "https://example.com/mid", "published": "2026-11-03"},
        ]
        out = scraper.prioritize_articles(articles, limit=2)
        self.assertEqual([x["url"] for x in out], ["https://example.com/new", "https://example.com/mid"])

    def test_immediate_start_to_cutoff_date_is_parsed(self):
        start, end, label = scraper.date_context("📍APP｜即起至11月12日", "2026-11-05T09:29:13+08:00")
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-11-05", "2026-11-12"))
        self.assertIn("即起", label)

    def test_double_eleven_day_is_parsed_as_november_11(self):
        start, end, label = scraper.date_context("雙11當天", "2026-11-05")
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-11-11", "2026-11-11"))
        self.assertEqual(label, "雙11當天")

    def test_nownews_6889553_keeps_store_and_app_periods_separate(self):
        url = "https://www.nownews.com/news/6889553"
        out = self._extract(
            "7-11咖啡買2送2！美式、拿鐵寄杯買11送11 全家單品拿鐵2杯95元",
            url,
            "2026-11-05T09:29:13+08:00",
            [
                "本週四咖啡優惠來了！7-11門市即起有濃萃美式買2送2、精品馥芮白買2送2。",
                "7-ELEVEN", "門市｜11月4日起至11月9日",
                "濃萃美式買2送2", "濃萃拿鐵買2送1", "厚乳拿鐵買2送1",
                "精品美式買2送2", "精品馥芮白買2送2", "黑糖珍珠撞奶買2送2",
                "📍APP｜即起至11月12日", "特大杯美式買11送11", "厚乳拿鐵買11送11",
                "全家", "門市｜11月6日至11月10日",
                "特大經典美式任2杯95元", "特大經典拿鐵任2杯95元",
                "中杯單品美式任2杯95元", "中杯單品拿鐵任2杯95元",
            ],
        )
        app = [x for x in out if "買11送11" in x["offer"]]
        stores = [x for x in out if x["store"] == "7-ELEVEN" and "買2送" in x["offer"]]
        family = [x for x in out if x["store"] == "全家"]
        self.assertEqual(len(app), 2)
        self.assertTrue(all((x["start_date"], x["end_date"]) == ("2026-11-05", "2026-11-12") for x in app))
        self.assertGreaterEqual(len(stores), 4)
        self.assertEqual(len(family), 4)
        self.assertTrue(all((x["start_date"], x["end_date"]) == ("2026-11-06", "2026-11-10") for x in family))
        self.assertFalse(any("本週四咖啡優惠來了" in x["offer"] for x in out))

    def test_yahoo_double11_article_separates_four_store_promotions(self):
        out = self._extract(
            "4大超商雙11「咖啡買11送11、珍奶買2送2」！再抽10萬元金豆",
            scraper.URL_YAHOO_DOUBLE11,
            "2026-11-05T19:15:00+08:00",
            [
                "4大超商雙11優惠一次看！7-ELEVEN特大美式買11送11，珍珠撞奶買2送2；全家特大杯美式/拿鐵任選2杯95元。",
                "7-ELEVEN",
                "OPENPOINT行動隨時取活動11月3日至11月12日歡慶雙十一",
                "CITY CAFE特大美式買11送11",
                "CITY CAFE特大厚乳拿鐵買11送11",
                "7-ELEVEN門市現茶飲優惠",
                "11月4日至11月9日黑糖珍珠撞奶買2送2",
                "全家", "11月6日至11月10日",
                "特大杯美式任選2杯95元", "特大杯拿鐵任選2杯95元",
                "萊爾富", "11月11日至12月8日",
                "Hi café大杯美式38杯搭配茶葉蛋38顆特價1,111元",
                "OKmart", "雙11當天", "大杯極淬莊園美式、拿鐵買2送2",
            ],
        )
        self.assertFalse(any("4大超商雙11優惠一次看" in x["offer"] for x in out))
        self.assertTrue(any(x["store"] == "7-ELEVEN" and "買11送11" in x["offer"] and x["start_date"] == "2026-11-03" for x in out))
        self.assertTrue(any(x["store"] == "全家" and "美式" in x["offer"] and x["start_date"] == "2026-11-06" for x in out))
        self.assertTrue(any(x["store"] == "萊爾富" and "38杯" in x["offer"] and x["start_date"] == "2026-11-11" for x in out))
        self.assertTrue(any(x["store"] == "OKmart" and x["start_date"] == "2026-11-11" and x["end_date"] == "2026-11-11" for x in out))
        stores = {x["store"] for x in out}
        self.assertTrue({"7-ELEVEN", "全家", "萊爾富", "OKmart"}.issubset(stores))

    def test_nownews_6889517_family_canned_coffee_is_not_misattributed(self):
        out = self._extract(
            "限5天！7-11雙11「超級多買1送1」全家咖啡15元",
            "https://www.nownews.com/news/6889517",
            "2026-11-05T00:07:00+08:00",
            [
                "7-ELEVEN",
                "11月4日至11月9日限時促銷",
                "門市現煮咖啡也有買2送2，大杯濃萃美式平均25元、大杯精品美式平均50元",
                "全家便利商店",
                "全家連續5天5好康，最新一檔是11月6日至11月10日",
                "喬亞無糖黑咖啡15元",
            ],
        )
        family = [x for x in out if "喬亞無糖黑咖啡" in x["offer"]]
        self.assertEqual(len(family), 1)
        self.assertEqual(family[0]["store"], "全家")
        self.assertEqual((family[0]["start_date"], family[0]["end_date"]), ("2026-11-06", "2026-11-10"))

    def test_furui_bai_is_recognized_as_a_distinct_7eleven_coffee_product(self):
        data = [
            row('7-ELEVEN', '精品美式買2送2', '2026-11-04', '2026-11-09', 'https://news.example/french-white'),
            row('7-ELEVEN', '精品馥芮白買2送2', '2026-11-04', '2026-11-09', 'https://news.example/french-white'),
        ]
        out = scraper.deduplicate_deals(data)
        self.assertEqual(len(out), 2)
        self.assertTrue(any('馥芮白' in x['offer'] for x in out))
        self.assertEqual(scraper._product_identity('精品馥芮白買2送2')[0], frozenset({'馥芮白'}))

    def test_v616_artifact_versions_are_consistent(self):
        with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('content="v6.17"', html)
        with open(os.path.join(HERE, "deals.json"), encoding="utf-8") as f:
            snapshot = json.load(f)
        # deals.json can remain a last-known-good snapshot until a real online run succeeds.
        self.assertEqual(snapshot.get("processing_version"), "v6.17")


class V617CoreParserTests(unittest.TestCase):
    """v6.17 核心解析器：非重疊 Span、中文數字、品牌／通路作用域與公平排程。"""

    def test_chinese_numerals_support_compound_values(self):
        cases = {"二": 2, "兩": 2, "十六": 16, "十九": 19, "二十一": 21,
                 "二十五": 25, "一百零二": 102, "711": 711}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(scraper.parse_zh_or_int(raw), expected)

    def test_date_is_masked_but_buy_gift_survives_double_eleven(self):
        text = "11/11 買11送11，活動限量"
        found = scraper.extract_offers_non_overlapping(text)
        self.assertEqual([x["mechanism"] for x in found], ["buy_x_get_y"])
        self.assertEqual((found[0]["buy"], found[0]["get"]), (11, 11))
        self.assertEqual(text[found[0]["span_start"]:found[0]["span_end"]], "買11送11")

    def test_second_cup_is_not_misread_as_two_cups_bundle(self):
        found = scraper.extract_offers_non_overlapping("第 2 杯 11 元")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["mechanism"], "second_cup_discount")
        self.assertEqual(found[0]["value"], 11)
        self.assertFalse(any(x["mechanism"] == "n_cups_fixed_price" for x in found))

    def test_chinese_buy_gift_and_bundle_price_are_parsed(self):
        buy = scraper.extract_offers_non_overlapping("買二送一")
        bundle = scraper.extract_offers_non_overlapping("任選十九杯711元")
        self.assertEqual((buy[0]["buy"], buy[0]["get"]), (2, 1))
        self.assertEqual((bundle[0]["count"], bundle[0]["price"]), (19, 711))

    def test_flat_discount_and_second_cup_half_price_are_distinct(self):
        flat = scraper.extract_offers_non_overlapping("單杯現折10元")
        second = scraper.extract_offers_non_overlapping("第二杯5折")
        self.assertEqual(flat[0]["mechanism"], "flat_discount")
        self.assertEqual(flat[0]["amount"], 10)
        self.assertEqual(second[0]["mechanism"], "second_cup_discount")
        self.assertEqual((second[0]["value"], second[0]["unit"]), (5, "折"))

    def test_bold_brand_prefix_inside_paragraph_switches_scope(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup('<article><p><strong>7-ELEVEN：</strong>門市特大美式買2送2。</p><p><strong>【全家】</strong>特大美式任選2杯95元。</p></article>', "html.parser")
        scoped = scraper.scope_article_blocks(scraper.extract_dom_article_blocks(soup))
        self.assertEqual(scoped[0]["brand"], "7-ELEVEN")
        self.assertEqual(scoped[-1]["brand"], "全家")

    def test_711_bundle_price_is_not_a_7eleven_brand_switch(self):
        scoped = scraper.scope_article_blocks(["【萊爾富】", "大杯卡布奇諾19杯711元"])
        self.assertEqual(scoped[-1]["brand"], "萊爾富")
        self.assertFalse(scoped[-1]["neutral_intro"])

    def test_multi_brand_intro_clears_previous_brand_context(self):
        scoped = scraper.scope_article_blocks([
            "【7-ELEVEN】",
            "雙11到了，7-ELEVEN、全家、萊爾富各推優惠",
            "特大美式買11送11",
        ])
        self.assertTrue(scoped[1]["neutral_intro"])
        self.assertIsNone(scoped[1]["brand"])
        self.assertIsNone(scoped[2]["brand"])

    def test_channel_scope_inherits_within_brand_and_resets_on_brand_change(self):
        scoped = scraper.scope_article_blocks([
            "【7-ELEVEN】", "OPENPOINT APP 行動隨時取", "特大美式買11送11",
            "【全家】", "特大經典美式任選2杯95元",
        ])
        self.assertEqual(scoped[2]["channel_scope"], "app")
        self.assertEqual(scoped[4]["channel_scope"], "unknown")

    def test_make_deal_persists_channel_scope_as_top_level_field(self):
        deal = scraper.make_deal("7-ELEVEN", "特大美式買11送11", "https://example.com/a",
                                 "測試", channel_scope="app", channel_scope_text="OPENPOINT APP")
        self.assertEqual(deal["channel_scope"], "app")
        self.assertEqual(deal["channel_scope_text"], "OPENPOINT APP")

    def test_fair_scheduler_round_robins_eleven_brands_and_respects_source_cap(self):
        brands = scraper.STORE_ORDER[:11]
        articles = []
        for brand in brands:
            for i in range(30):
                articles.append({"url": f"https://{brand.replace(' ', '').replace('/', '')}.example/{i}",
                                 "title": f"{brand} 咖啡優惠 {i}", "published": f"2026-11-{(i % 8) + 1:02d}",
                                 "brand_hints": [brand], "source_bucket": brand})
        scheduled = scraper.schedule_fair_article_quota(articles, max_total=160, max_per_source=25)
        self.assertEqual(len(scheduled), 160)
        counts = {brand: sum(1 for item in scheduled if item.get("scheduled_for_brand") == brand)
                  for brand in brands}
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        sources = {}
        for item in scheduled:
            source = item["scheduled_source_bucket"]
            sources[source] = sources.get(source, 0) + 1
        self.assertTrue(all(value <= 25 for value in sources.values()))

    def test_cross_brand_same_url_is_scheduled_once(self):
        articles = [
            {"url": "https://example.com/shared", "title": "四大超商咖啡優惠", "published": "2026-11-08",
             "brand_hints": ["7-ELEVEN", "全家", "萊爾富", "OKmart"], "source_bucket": "Yahoo"},
            {"url": "https://example.com/shared?utm_source=google", "title": "四大超商咖啡優惠", "published": "2026-11-08",
             "brand_hints": ["7-ELEVEN", "全家"], "source_bucket": "GoogleNews"},
        ]
        scheduled = scraper.schedule_fair_article_quota(articles, max_total=10, max_per_source=25)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(set(scheduled[0]["brand_hints"]), {"7-ELEVEN", "全家", "萊爾富", "OKmart"})

    def test_static_html_fixtures_are_parseable_without_network(self):
        from bs4 import BeautifulSoup
        fixture_dir = os.path.join(HERE, "tests", "fixtures")
        files = ["nownews_6888826.html", "nownews_6889517.html", "nownews_6889553.html", "yahoo_double11_4stores.html"]
        self.assertTrue(all(os.path.isfile(os.path.join(fixture_dir, name)) for name in files))
        expected = {
            "nownews_6888826.html": {"7-ELEVEN", "全家"},
            "nownews_6889517.html": {"7-ELEVEN", "全家"},
            "nownews_6889553.html": {"7-ELEVEN", "全家"},
            "yahoo_double11_4stores.html": {"7-ELEVEN", "全家", "萊爾富", "OKmart"},
        }
        for filename, expected_brands in expected.items():
            with open(os.path.join(fixture_dir, filename), encoding="utf-8") as fixture:
                soup = BeautifulSoup(fixture.read(), "html.parser")
            blocks = scraper.extract_dom_article_blocks(soup)
            scoped = scraper.scope_article_blocks(blocks)
            brands = {x["brand"] for x in scoped if x.get("brand")}
            self.assertTrue(expected_brands.issubset(brands), (filename, brands))
        with open(os.path.join(fixture_dir, "yahoo_double11_4stores.html"), encoding="utf-8") as fixture:
            soup = BeautifulSoup(fixture.read(), "html.parser")
        scoped = scraper.scope_article_blocks(scraper.extract_dom_article_blocks(soup))
        self.assertTrue(any(x["brand"] == "7-ELEVEN" and x["channel_scope"] == "app" for x in scoped))

    def test_snapshot_schema_and_version_are_v617(self):
        with open(os.path.join(HERE, "deals.json"), encoding="utf-8") as f:
            snapshot = json.load(f)
        self.assertEqual(snapshot.get("processing_version"), "v6.17")
        self.assertEqual(snapshot.get("count"), len(snapshot.get("deals", [])))
        self.assertTrue(all("channel_scope" in item for item in snapshot.get("deals", [])))
        self.assertTrue(all(item["channel_scope"] in {"app", "store", "delivery", "unknown"}
                            for item in snapshot.get("deals", [])))



    def test_official_probe_classifies_403_without_throwing(self):
        import importlib.util
        from unittest.mock import Mock
        path = os.path.join(HERE, "tools", "probe_official_sources.py")
        spec = importlib.util.spec_from_file_location("probe_official_sources", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        response = Mock()
        response.status_code = 403
        response.content = b"<html><body>Forbidden</body></html>"
        response.url = "https://www.7-11.com.tw/"
        response.headers = {"Content-Type": "text/html"}
        response.ok = False
        session = Mock()
        session.get.return_value = response
        result = module.inspect_url(session, "7-ELEVEN", response.url, timeout=1)
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["result"], "blocked_or_shell")
        self.assertEqual(result["response_bytes"], len(response.content))
