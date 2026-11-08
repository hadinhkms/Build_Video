import re
import unittest
from src.text.vi_normalizer import VietnameseNormalizer

class TestVietnameseNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = VietnameseNormalizer(pronunciations_path="config/pronunciations.json")

    def test_01_currency_k(self):
        res = self.normalizer.normalize("Giá chiếc áo là 50k.")
        self.assertIn("năm mươi nghìn", res.voice_text)
        self.assertNotIn("50k", res.voice_text)

    def test_02_currency_dong(self):
        res = self.normalizer.normalize("Tôi có 50.000đ trong ví.")
        self.assertIn("năm mươi nghìn đồng", res.voice_text)
        self.assertNotIn("50.000đ", res.voice_text)

    def test_03_currency_dollar_prefix(self):
        res = self.normalizer.normalize("Cái bánh giá $5.")
        self.assertIn("năm đô la", res.voice_text)
        self.assertNotIn("$5", res.voice_text)

    def test_04_currency_vnd_words(self):
        res = self.normalizer.normalize("Thu nhập 2 triệu VNĐ.")
        self.assertIn("hai triệu đồng", res.voice_text)
        self.assertNotIn("VNĐ", res.voice_text)

    def test_05_percentage_integer(self):
        res = self.normalizer.normalize("Đạt 50% chỉ tiêu.")
        self.assertIn("năm mươi phần trăm", res.voice_text)
        self.assertNotIn("%", res.voice_text)

    def test_06_percentage_decimal(self):
        res = self.normalizer.normalize("Tỷ lệ 82,7% tán thành.")
        self.assertIn("tám mươi hai phẩy bảy phần trăm", res.voice_text)

    def test_07_percentage_range(self):
        res = self.normalizer.normalize("Khoảng 10-15% số người.")
        self.assertIn("mười đến mười lăm phần trăm", res.voice_text)

    def test_08_thousands_separator(self):
        res = self.normalizer.normalize("Có 1.500 người tham dự.")
        self.assertIn("một nghìn năm trăm người", res.voice_text)
        self.assertNotIn("1.500", res.voice_text)

    def test_09_decimal_comma(self):
        res = self.normalizer.normalize("Quãng đường 3,5 km.")
        self.assertIn("ba phẩy năm ki lô mét", res.voice_text)
        self.assertNotIn("3,5", res.voice_text)

    def test_10_version_dots(self):
        res = self.normalizer.normalize("Cập nhật iOS 18.2 và GPT 5.5.")
        self.assertIn("mười tám chấm hai", res.voice_text)
        self.assertIn("năm chấm năm", res.voice_text)

    def test_11_full_date(self):
        res = self.normalizer.normalize("Hôm nay là 10/5/2024.")
        self.assertIn("mười tháng năm năm hai nghìn không trăm hai mươi tư", res.voice_text)

    def test_12_day_month(self):
        res = self.normalizer.normalize("Sự kiện ngày 5/10.")
        self.assertIn("ngày năm tháng mười", res.voice_text)

    def test_13_thang_four(self):
        res = self.normalizer.normalize("Thời tiết tháng 4 rất đẹp.")
        self.assertIn("tháng tư", res.voice_text)

    def test_14_thang_other(self):
        res = self.normalizer.normalize("Sinh vào tháng 10.")
        self.assertIn("tháng mười", res.voice_text)

    def test_15_thu_two(self):
        res = self.normalizer.normalize("Hẹn gặp thứ 2.")
        self.assertIn("thứ hai", res.voice_text)

    def test_16_thu_four(self):
        res = self.normalizer.normalize("Lịch họp vào thứ 4.")
        self.assertIn("thứ tư", res.voice_text)

    def test_17_thu_one(self):
        res = self.normalizer.normalize("Bước thứ 1 cần làm.")
        self.assertIn("thứ nhất", res.voice_text)

    def test_18_thu_seven(self):
        res = self.normalizer.normalize("Nghỉ vào thứ 7.")
        self.assertIn("thứ bảy", res.voice_text)

    def test_19_time_h_colon(self):
        res = self.normalizer.normalize("Bắt đầu lúc 7h30.")
        self.assertIn("bảy giờ ba mươi", res.voice_text)

    def test_20_time_colon_format(self):
        res = self.normalizer.normalize("Tàu chạy lúc 19:05.")
        self.assertIn("mười chín giờ không năm phút", res.voice_text)

    def test_21_time_colon_half(self):
        res = self.normalizer.normalize("Hẹn nhau lúc 19:30.")
        self.assertIn("mười chín giờ ba mươi phút", res.voice_text)

    def test_22_units_kg(self):
        res = self.normalizer.normalize("Cân nặng 65 kg.")
        self.assertIn("sáu mươi lăm ki lô gam", res.voice_text)

    def test_23_units_cm(self):
        res = self.normalizer.normalize("Dài 15 cm.")
        self.assertIn("mười lăm xen ti mét", res.voice_text)

    def test_24_units_temp(self):
        res = self.normalizer.normalize("Nhiệt độ 30 °C.")
        self.assertIn("ba mươi độ xê", res.voice_text)

    def test_25_roman_chuong(self):
        res = self.normalizer.normalize("Đọc Chương IV quyển sách.")
        self.assertIn("Chương bốn", res.voice_text)

    def test_26_roman_hoi(self):
        res = self.normalizer.normalize("Xem Hồi II câu chuyện.")
        self.assertIn("Hồi hai", res.voice_text)

    def test_27_roman_the_ky(self):
        res = self.normalizer.normalize("Vào Thế kỷ XXI hiện đại.")
        self.assertIn("Thế kỷ hai mươi mốt", res.voice_text)

    def test_28_number_range(self):
        res = self.normalizer.normalize("Có khoảng 3-4 người đứng đợi.")
        self.assertIn("ba đến bốn người", res.voice_text)

    def test_29_abbreviation_tphcm(self):
        res = self.normalizer.normalize("Tôi sống tại TP.HCM.")
        self.assertIn("thành phố Hồ Chí Minh", res.voice_text)

    def test_30_abbreviation_ko(self):
        res = self.normalizer.normalize("Tôi ko đồng ý.")
        self.assertIn("không đồng ý", res.voice_text)

    def test_31_symbol_ampersand(self):
        res = self.normalizer.normalize("Nam & Mai cùng đi.")
        self.assertIn("Nam và Mai", res.voice_text)
        self.assertNotIn("&", res.voice_text)

    def test_32_symbol_plus(self):
        res = self.normalizer.normalize("Một + một bằng hai.")
        self.assertIn("Một cộng một", res.voice_text)
        self.assertNotIn("+", res.voice_text)

    def test_33_symbol_arrow(self):
        res = self.normalizer.normalize("Đi từ A -> B hoặc A → B.")
        self.assertNotIn("->", res.voice_text)
        self.assertNotIn("→", res.voice_text)

    def test_34_emoji_removed(self):
        res = self.normalizer.normalize("Chào buổi sáng! 😊🔥")
        self.assertEqual(res.voice_text, "Chào buổi sáng!")

    def test_35_url_removed(self):
        res = self.normalizer.normalize("Xem chi tiết tại https://example.com/test nhé.")
        self.assertNotIn("https://", res.voice_text)

    def test_36_number_21(self):
        res = self.normalizer.normalize("Anh ấy 21 tuổi.")
        self.assertIn("hai mươi mốt tuổi", res.voice_text)

    def test_37_number_105(self):
        res = self.normalizer.normalize("Căn phòng số 105.")
        self.assertIn("một trăm linh năm", res.voice_text)

    def test_38_number_2026(self):
        res = self.normalizer.normalize("Chào mừng năm 2026.")
        self.assertIn("năm hai nghìn không trăm hai mươi sáu", res.voice_text)

    def test_39_phone_number(self):
        res = self.normalizer.normalize("Số điện thoại 0912345678 của tôi.")
        self.assertIn("không chín một hai ba bốn năm sáu bảy tám", res.voice_text)

    def test_40_punctuation_preserved(self):
        text = "Trời mưa... Tôi nghe tiếng sấm! Anh có đó không? Thật ư, tôi không tin."
        res = self.normalizer.normalize(text)
        self.assertIn("...", res.voice_text)
        self.assertIn("!", res.voice_text)
        self.assertIn("?", res.voice_text)
        self.assertIn(",", res.voice_text)
        self.assertIn(".", res.voice_text)

    def test_41_sample_chapter_unmodified(self):
        text = "Cơn mưa cuối tháng Mười trút xuống mái hiên rầm rập."
        res = self.normalizer.normalize(text)
        self.assertEqual(res.voice_text, text)

    def test_42_regression_no_digits_or_bad_symbols(self):
        corpus = [
            "Giá 50k lúc 7h30 ngày 10/5/2024 ở TP.HCM giảm 15% còn $40đ.",
            "Chương IV: Nam & Mai đi 3,5 km trong 2h.",
            "Tập II: 1.500 người đạt 82,7% chỉ tiêu năm 2026."
        ]
        bad_pattern = re.compile(r'[0-9%$#&@→]')
        for text in corpus:
            res = self.normalizer.normalize(text)
            matches = bad_pattern.findall(res.voice_text)
            self.assertEqual(len(matches), 0, f"Found forbidden chars {matches} in: '{res.voice_text}'")

    def test_43_spans_mapping(self):
        raw = "Chào năm 2026."
        res = self.normalizer.normalize(raw)
        self.assertGreater(len(res.spans), 0)
        span = res.spans[0]
        self.assertEqual(raw[span.raw_start:span.raw_end], "2026")
    def test_44_large_numbers_trillions(self):
        from src.text.vi_numbers import read_integer
        self.assertEqual(read_integer(1_000_000_000_000), "một nghìn tỷ")
        self.assertEqual(read_integer(1_500_000_000_000), "một nghìn năm trăm tỷ")
        self.assertEqual(read_integer(2_000_000_000_000_000), "hai triệu tỷ")

if __name__ == "__main__":
    unittest.main()
