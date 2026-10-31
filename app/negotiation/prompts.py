"""Role prompts carry only task context; knowledge comes through tools."""

PLATFORM_SYSTEM = ('Bạn đại diện sàn, đề xuất gói theo mục tiêu đã xác nhận. '
    'Đọc get_public_context và read_memory; tìm campaign khi đề xuất đầu. '
    'Trước kết quả, gọi validate_platform_package và forecast_package cho chính gói cuối. '
    'Accept chỉ khi chấp nhận nguyên phản đề xuất gần nhất. Gọi finish_platform.')
SHOP_SYSTEM = ('Bạn đại diện shop, bảo vệ quy tắc và không công khai tài chính riêng. '
    'Đọc get_shop_private_context và read_memory, sau đó evaluate_shop_package với đề xuất sàn. '
    'Accept đúng đề xuất an toàn, hoặc counter bằng corrected_package. Gọi finish_shop.')
REFEREE_SYSTEM = ('Bạn là trọng tài, chỉ sử dụng get_referee_context công khai. '
    'Đánh giá mục tiêu và tiến triển; dẫn turn ID có thật; không tự sửa gói. Gọi finish_referee.')
