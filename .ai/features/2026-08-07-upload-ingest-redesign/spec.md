# Thiết kế lại luồng tải lên → nạp dữ liệu

## Problem Statement

Cán bộ nhận bộ file quyết toán của một doanh nghiệp và phải đưa được chúng vào hệ thống cho tới khi **đủ dữ liệu để chạy kiểm tra**. Hiện tại việc đó đi qua bốn màn hình rời nhau và không màn nào trả lời được câu hỏi duy nhất cán bộ cần trả lời: *còn thiếu gì nữa?*

Cụ thể, những gì cán bộ gặp hôm nay:

- **Không biết bao giờ là đủ.** Trang tài liệu nói "Đã nạp một phần · 3/4 loại". Nhưng đủ 4 loại không có nghĩa là kiểm tra chạy được: một kỳ có thể đủ cả 4 loại mà vẫn thiếu ba tháng dòng tờ khai, và kiểm tra vẫn chạy trên phần khuyết đó.
- **Bị đá sang trang khác để xem kết quả.** Tải file lên xong bị chuyển sang trang công việc — một bản ghi kỹ thuật gồm mốc thời gian và bảng khoá/giá trị. Ba trong bốn kết cục của việc nạp kết thúc bằng một câu bảo cán bộ quay lại trang khác để xử lý.
- **Vướng mắc không nói được cách gỡ.** Khi một kiểm tra không chạy được, hệ thống in ra một câu lý do. Đo trên dữ liệu thật: trong 10 lần một kiểm tra không kết luận được, chỉ **1 lần** cách gỡ là nạp thêm file của chính kỳ đó. 6 lần cần dữ liệu kỳ khác hoặc một xác nhận về doanh nghiệp, 3 lần **không có gì nạp thêm được** — đó là kết luận về doanh nghiệp chứ không phải lỗ hổng dữ liệu. Cán bộ đọc cùng một dạng câu và không phân biệt được ba tình huống đó.
- **Đặt file vào ô sai không ai báo.** Form tải lên bắt cán bộ tự chọn file nào vào ô nào. Chọn sai thì hỏng ở bước đọc, sau vài phút.
- **Xem trước file gần như vô dụng đúng lúc cần nhất.** Lưới xem trước cắt ở 40 cột trong khi **52 trên 170 trang tính đo được vượt 40 cột** (rộng nhất 257 cột) — mà việc của màn đó chính là xác nhận cột nào là cột nào. File nặng hơn 25MB thì không dựng lưới, tức **11 trên 493 file** không xem được, và đó đúng là các file tờ khai lớn.
- **Xoá file xong không có gì thay đổi.** Dòng đã nạp vẫn nguyên, số liệu vẫn hiện, điểm rủi ro vẫn xếp hạng như cũ, không dấu hiệu nào cho biết dữ liệu đang dùng là của bộ file không còn tồn tại.
- **Doanh nghiệp nhiều sổ không nạp được qua web.** Việc gán sổ quyết toán nằm trong màn sửa cột của từng file, trong khi điều kiện lại là toàn kỳ và tất-cả-hoặc-không.

## Solution

Một màn hình duy nhất cho mỗi doanh nghiệp, hiện **mọi kỳ cùng lúc**, đếm ngược tới trạng thái "đủ dữ liệu", và nói rõ từng vướng mắc gỡ bằng cách nào.

- "Đủ" được định nghĩa lại: **mọi kiểm tra áp dụng cho doanh nghiệp này đều có đủ nguồn dữ liệu đầu vào**. Không phải "đủ 4 loại tài liệu".
- Mỗi vướng mắc được xếp theo **cách gỡ**, không theo lý do: nạp thêm file kỳ này · cần kỳ khác hoặc một xác nhận · không nạp gì thêm được (đây là phát hiện, xem kiểm tra tương ứng).
- Tải file lên bằng **một ô thả duy nhất cho mỗi kỳ**. Hệ thống **gợi ý** loại cho từng file và nói rõ căn cứ gợi ý, cán bộ sửa được trước khi nạp.
- Tiến trình nạp và kết quả hiện **ngay tại dòng kỳ đó**, không chuyển trang.
- Xem trước file thành một **lưới cuộn được**, không giới hạn cột, không giới hạn kích thước file, kèm hai công tắc: *hiện cột hệ thống đang đọc* và *hiện công thức trong ô*.
- Kết quả kiểm tra dựa trên dữ liệu đã đổi được **đánh dấu là cũ** ở mọi chỗ con số xuất hiện, kể cả bảng xếp hạng doanh nghiệp.

## User Stories

1. Là cán bộ, tôi muốn mở một màn hình duy nhất của doanh nghiệp và thấy mọi kỳ cùng lúc, để biết ngay kỳ nào đã sẵn sàng và kỳ nào chưa mà không phải mở từng khối một.
2. Là cán bộ, tôi muốn mỗi kỳ nói rõ "đủ dữ liệu cho N trên M kiểm tra", để tôi biết mình đang ở đâu so với đích thay vì chỉ biết đã nạp mấy loại tài liệu.
3. Là cán bộ, tôi muốn con số đó tính được ngay khi vừa nạp xong, không phải chạy kiểm tra trước, để tôi biết còn thiếu gì trước khi bỏ ra vài phút chạy.
4. Là cán bộ, tôi muốn các vướng mắc được xếp theo cách gỡ, để tôi biết cái nào giải quyết bằng cách tải thêm file và cái nào thì không.
5. Là cán bộ, tôi muốn nhóm "nạp thêm file kỳ này" kèm nút tải lên ngay tại đó, để không phải đi tìm chỗ tải.
6. Là cán bộ, tôi muốn nhóm "cần kỳ khác hoặc xác nhận" kèm nút mở đúng kỳ cần nạp, để không phải tự suy ra kỳ nào.
7. Là cán bộ, tôi muốn xác nhận "năm đầu nộp BCQT" ngay trên màn dữ liệu, vì đó là thứ đang chặn kỳ sớm nhất của mọi doanh nghiệp, chứ không phải đi vào trang sửa doanh nghiệp mới thấy.
8. Là cán bộ, tôi muốn vướng mắc không gỡ được bằng dữ liệu ghi rõ là phát hiện về doanh nghiệp và trỏ sang kiểm tra tương ứng, để tôi thôi đi tìm file không tồn tại.
9. Là cán bộ, tôi muốn thấy niên độ và ngày quyết định kiểm tra sau thông quan ở đầu màn, vì đó là thuộc tính của doanh nghiệp chứ không của một kỳ.
10. Là cán bộ, tôi muốn thả cả bộ file của một kỳ vào một ô duy nhất, để không phải quyết định file nào vào ô nào.
11. Là cán bộ, tôi muốn hệ thống gợi ý loại cho từng file đã thả, để tôi chỉ phải sửa chỗ nó đoán sai.
12. Là cán bộ, tôi muốn mỗi gợi ý nói rõ căn cứ — theo tên file hay đã mở file và khớp bố cục — để tôi biết chỗ nào cần tự kiểm.
13. Là cán bộ, tôi muốn file hệ thống không đoán được loại thì nằm riêng và bắt tôi chọn, chứ không bị gán bừa.
14. Là cán bộ, tôi muốn sửa được loại của bất kỳ file nào trước khi bấm nạp, để không phải xoá đi thả lại.
15. Là cán bộ của doanh nghiệp nhiều sổ, tôi muốn gán sổ quyết toán cho từng file quyết toán ngay ở màn thả file, để không bị từ chối nạp sau khi đã chờ.
16. Là cán bộ, tôi muốn nút nạp bị khoá khi còn file quyết toán chưa gán sổ, kèm câu nói rõ còn thiếu file nào, để biết phải làm gì trước.
17. Là cán bộ, tôi muốn gán lại sổ cho file đã nằm sẵn trong hệ thống, để doanh nghiệp đã nạp bằng dòng lệnh trước đây vẫn nạp lại được qua web.
18. Là cán bộ, tôi muốn thấy tiến trình nạp ngay tại dòng kỳ, để không bị chuyển sang một trang khác rồi phải tự tìm đường về.
19. Là cán bộ, tôi muốn phân biệt được kỳ đang chờ trong hàng đợi với kỳ đang chạy, vì hệ thống chỉ chạy một việc nạp một lúc.
20. Là cán bộ, tôi muốn kết quả nạp — kể cả khi hỏng — hiện ngay tại dòng kỳ đó cùng chỗ với nút xử lý, để không phải đọc một câu rồi đi sang trang khác.
21. Là cán bộ, tôi muốn khi file không đọc được thì thấy ngay nút chọn trang tính và nút nhờ AI chẩn đoán, để xử lý tại chỗ.
22. Là cán bộ, tôi muốn hệ thống chỉ hỏi xác nhận vị trí cột **lần đầu** gặp một cấu trúc biểu **của doanh nghiệp này**, để các kỳ sau của cùng doanh nghiệp không hỏi lại.
23. Là cán bộ, tôi muốn biết vì sao mình bị hỏi — cột nào, kiểm tra nào đọc cột đó — để biết việc xác nhận này ảnh hưởng gì.
24. Là cán bộ, tôi muốn mỗi kỳ mở ra thấy số dòng theo từng loại tài liệu, để biết loại nào mỏng bất thường.
25. Là cán bộ, tôi muốn thấy danh sách file thật đã tải lên và mỗi file phục vụ những loại nào, vì một workbook có thể vừa là Mẫu 15 vừa là Mẫu 15a vừa là Mẫu 16.
26. Là cán bộ, tôi không muốn cùng một con số dòng lặp lại ở nhiều file của cùng một loại, vì đọc thành tổng gấp đôi.
27. Là cán bộ, tôi muốn dòng file chỉ hiện thứ có hệ quả — cần xác nhận, đọc hỏng, có cảnh báo — để không phải lọc qua một dãy nhãn không đòi hỏi gì.
28. Là cán bộ, tôi muốn mở trang riêng của một file để xem đầy đủ căn cứ hệ thống đã đọc file đó bằng cách nào.
29. Là cán bộ, tôi muốn xem trước file bằng lưới cuộn được cả ngang lẫn dọc, để tới được cột thứ 257 và dòng thứ 200.000.
30. Là cán bộ, tôi muốn xem trước được cả file nặng, vì file tờ khai lớn đúng là loại tôi cần soát nhất.
31. Là cán bộ, tôi muốn bật "hiện cột hệ thống đang đọc" để thấy cột nào đang được đọc thành trường gì.
32. Là cán bộ, tôi muốn bật "hiện công thức trong ô" để phát hiện ô chứa công thức thay vì số — đây là dạng lỗi từng làm mất 28,5 tỷ mà không kiểm tra nào bắt được.
33. Là cán bộ, tôi muốn nhảy tới một dòng cụ thể trong lưới, để đối chiếu với dòng mà một phát hiện trỏ tới.
34. Là cán bộ, tôi muốn xác nhận vị trí cột ngay trên lưới đó, chứ không phải trên một lưới rút gọn 15 dòng ở màn khác.
35. Là cán bộ, tôi muốn một file chỉ có một địa chỉ để mở, để gửi được cho đồng nghiệp và quay lại được.
36. Là cán bộ, tôi muốn khi xoá hoặc thay một file thì kỳ đó nói rõ dữ liệu đang dùng không còn khớp bộ file, để không đọc nhầm số cũ là số hiện hành.
37. Là cán bộ, tôi muốn có nút nạp lại ngay tại chỗ cảnh báo đó, để gỡ luôn.
38. Là cán bộ, tôi muốn kết quả kiểm tra được đánh dấu là cũ khi dữ liệu nền đã đổi, để biết cần chạy lại.
39. Là cán bộ, tôi muốn dấu hiệu cũ đó xuất hiện cả ở bảng xếp hạng doanh nghiệp, vì đó là nơi tôi so sánh doanh nghiệp với nhau.
40. Là cán bộ, tôi muốn doanh nghiệp có kết quả cũ vẫn nằm trong bảng xếp hạng kèm dấu hiệu, chứ không biến mất, vì biến mất làm doanh nghiệp đó trông sạch hơn thực tế.
41. Là cán bộ, tôi muốn thấy kỳ báo cáo ngay trên dòng kỳ khi kỳ đó không phải năm dương lịch, để không hiểu nhầm nhãn năm.
42. Là cán bộ, tôi muốn khoảng ngày thiếu dòng tờ khai xuất hiện như một vướng mắc có cách gỡ, chứ không phải một khối cảnh báo riêng lẻ.
43. Là cán bộ, tôi muốn sửa cửa sổ kỳ ngay trên dòng kỳ, không phải mở một khối riêng.
44. Là cán bộ, tôi muốn đường dẫn cũ tới trang tải lên vẫn dẫn tới đâu đó dùng được, để các liên kết đã lưu không hỏng.
45. Là cán bộ mới, tôi muốn một doanh nghiệp chưa có gì cũng hiện màn dữ liệu với lời mời thêm kỳ, để biết bắt đầu từ đâu.
46. Là cán bộ, tôi muốn hệ thống bảo "bấm nạp" khi file đã có mà chưa đọc, chứ không bảo tôi tải lên lần nữa thứ tôi vừa tải.
47. Là cán bộ, tôi muốn xem trước được cả file mang đuôi `.xls` nhưng thật ra là XML, vì đó là 38 file trong kho và hiện không mở được cái nào.
48. Là cán bộ, tôi muốn khi hệ thống không nhận ra định dạng thì nó nói định dạng thật nó dò được, chứ không nhắc lại cái đuôi file vốn đang sai.
49. Là cán bộ, tôi muốn được nói thẳng rằng file `.xls` cũ không đọc được công thức, thay vì thấy một lưới rỗng và tự đoán.
50. Là cán bộ, tôi muốn file xem trước được nhưng chưa nạp được thì ghi rõ như vậy, để không tưởng đã nạp xong.
51. Là cán bộ, tôi muốn kiểm tra mà hệ thống không đoán trước được vẫn nằm trong mẫu số kèm chữ "biết khi chạy", để mẫu số không tự co lại làm doanh nghiệp trông sạch hơn.
52. Là cán bộ, tôi muốn lần mở lưới đầu tiên của một file lớn mất vài giây một lần rồi sau đó nhảy dòng tức thì, thay vì mỗi lần cuộn sâu lại chờ.

## Implementation Decisions

### 1. Định nghĩa "đủ dữ liệu"

Một kỳ **đủ dữ liệu** khi mọi kiểm tra áp dụng cho doanh nghiệp đó đều có đủ nguồn Tầng 1 mà nó khai cần. Không dùng số loại tài liệu làm thước đo. Nhãn trạng thái theo số loại tài liệu bị thay bằng số kiểm tra có đủ đầu vào.

Con số này tính được từ trạng thái DB, không cần chạy kiểm tra: đối chiếu nguồn mỗi kiểm tra khai cần với tập nguồn đang có dòng cho (doanh nghiệp, kỳ).

### 2. Cách gỡ trở thành một khái niệm có tên

Trạng thái "chưa đánh giá được" hiện chỉ mang một câu lý do tự do. Bổ sung **lớp cách gỡ** — một trong ba giá trị:

- `need-file-this-period` — thiếu nguồn Tầng 1 của chính kỳ này.
- `need-other-period-or-confirmation` — cần dữ liệu kỳ khác, hoặc một xác nhận ở mức doanh nghiệp (điển hình: năm đầu nộp BCQT).
- `nothing-to-load` — không có gì nạp thêm được; đây là kết luận về doanh nghiệp, thuộc về màn phát hiện.

Lớp này gắn tại chỗ kiểm tra **quyết định** là không đánh giá được, không suy từ mã kiểm tra: đo trên dữ liệu thật, riêng C4.3 sinh ra cả ba lớp tuỳ kỳ.

Hai ràng buộc đã xác minh, quyết định cách cài:

- **Có năm nguồn sinh trạng thái này, không phải bốn.** Ngoài bốn chỗ dựng kiểu trả về `NotEvaluable`, bộ điều phối còn tự ghi trạng thái + lý do thẳng từ cổng thiếu nguồn mà **không** dựng đối tượng nào — và đó chính là nguồn sinh ra lớp phổ biến nhất của bảng điều khiển. Thêm trường vào kiểu trả về là **không đủ**; lớp phải đi cùng đường ghi trạng thái.
- **Lớp là thuộc tính của từng lần, không phải của từng chỗ gọi.** Nhánh độ phủ định mức sinh lớp 2 hay lớp 3 tuỳ tình huống: cùng một câu lý do phủ cả "chưa khai ở kỳ này lẫn kỳ trước" (gỡ bằng cách nạp định mức kỳ trước) lẫn "chưa từng khai bao giờ" (là phát hiện). Không gán lớp tĩnh theo chỗ gọi được.

**Cách cài, để hai đường không thể lệch nhau:** kiểu trả về `NotEvaluable` nhận thêm trường lớp cách gỡ **bắt buộc**, kiểm giá trị theo đúng bộ ba. Đường thiếu nguồn trong bộ điều phối **dựng chính kiểu đó** thay vì tự ghi trạng thái, và bỏ hẳn lệnh ghi thẳng. Sau đó chỉ còn **một kiểu mang (lý do, lớp)** và **một đường lưu**. Bảng lần chạy kiểm tra thêm một cột lớp cách gỡ, cho phép rỗng — thêm cột thẳng, không dùng chế độ dựng lại bảng.

Lớp của cả năm nguồn:

| Nguồn | Lớp |
|---|---|
| Cổng thiếu nguồn ở bộ điều phối | 1 |
| Phân loại loại hình DN | **1** — BCCT hoặc M16 của chính kỳ này gỡ được |
| Đối chiếu liên kỳ | 2, đích là kỳ N−1 |
| Cổng định mức, nhánh kỳ biên | 2, đích là trường năm đầu nộp BCQT của DN |
| Cổng định mức, nhánh độ phủ | **theo từng lần**: lớp 2 nếu còn kỳ trước nào trong khoảng dữ liệu chưa có dòng định mức (định mức thiếu có thể nằm ở M16 chưa nạp); ngược lại lớp 3 |

Quy tắc của nhánh cuối là đơn điệu: **còn thứ nạp được thì cách gỡ là nạp nó; hết đường nạp mới là kết luận.**

Hàm phân loại trả về **(lớp, đích)** — đích là một kỳ, một trường của doanh nghiệp, hoặc một loại tài liệu. **Chỉ lưu lớp**, đích tính lại lúc hiển thị. Không có đích thì nút "mở đúng kỳ cần nạp" ở câu chuyện người dùng số 6 không có dữ liệu để dựng.

**Một phân loại, hai nơi đọc.** Màn dữ liệu tính lớp 1 và 2 trực tiếp từ DB (không cần lần chạy nào), còn màn phát hiện đọc lớp đã lưu. Hai đường này **phải dùng chung một hàm phân loại và một bộ từ vựng** — nếu tách đôi, con số trên màn dữ liệu sẽ lệch với trạng thái đã lưu.

### 3. Phạm vi đếm của màn dữ liệu, và bảy trạng thái nó phải phân biệt

Màn dữ liệu chỉ đếm lớp 1 và lớp 2. Lớp 3 không nằm trong phép đếm và không hiện như vướng mắc dữ liệu; nó xuất hiện ở màn phát hiện, nơi trạng thái "chưa đánh giá được" đã có chỗ hiển thị.

**Phép đếm vẫn đo theo DÒNG đã nạp**, vì kiểm tra đọc dòng — khả năng chạy được là sự thật về dòng. Nhưng **câu chữ cách gỡ phải tra bản ghi file trước khi chọn động từ**, nếu không hệ thống sẽ bảo cán bộ tải lên thứ họ vừa tải. Bảy trạng thái của một (loại tài liệu, kỳ):

1. Không có bản ghi file → *nạp thêm file kỳ này*.
2. Có file, chưa đọc lần nào → *bấm nạp*, không phải *tải thêm file*.
3. File đọc hỏng → vướng mắc ở mức file: sửa file hoặc chọn trang tính, dẫn sang trang file.
4. Đã phân tích, còn cột cần xác nhận → *xác nhận cột*, dẫn sang trang file. Đây chính là ca lượt nạp dừng ở cổng và ghi không dòng nào.
5. Đã phân tích, không vướng cột, nhưng còn file quyết toán chưa gán sổ → *gán sổ*. Trạng thái 4 và 5 phân biệt bằng cột vướng và tình trạng sổ, **không** phân biệt được chỉ bằng trạng thái đọc file.
6. Đã có dòng → nguồn sẵn sàng.
7. Có dòng nhưng bộ file đã đổi từ sau lượt nạp → **dấu hiệu cũ trên dòng kỳ, là một trục riêng, không bao giờ gộp vào phép đếm đủ**. Sau khi xoá file, "đủ dữ liệu" vẫn **đúng** — kiểm tra vẫn chạy được — chỉ là dữ liệu không còn khớp bộ file. Gộp hai thứ lại sẽ bảo cán bộ tải file trong khi việc cần làm là nạp lại.

Trạng thái 2–5 là vướng mắc ở **mức file**. Chúng hiện thành dòng trong danh sách vướng mắc nhưng **không** thuộc bộ ba lớp cách gỡ ở mục 2 — không thêm lớp thứ tư. Kiểm tra nào thiếu nguồn vì một vướng mắc mức file thì trỏ tới vướng mắc đó thay vì nhắc lại.

**Ba cổng mà bộ khai điều kiện không diễn đạt được** — kiểm tra cần "BCCT **hoặc** M16", kiểm tra đọc M15 **kỳ trước**, và cổng độ phủ định mức xuyên kỳ — được đánh giá **bằng cách gọi chính hàm điều kiện mà kiểm tra gọi**, không viết lại logic song song. Đây mới là cách "một hàm phân loại" ở mục 2 thành sự thật: bảng điều khiển và kiểm tra khớp nhau vì chạy cùng một đoạn mã.

Kiểm tra nào thật sự không dự đoán được thì **vẫn nằm trong mẫu số**, hiển thị "biết khi chạy". Không rút mẫu số — rút mẫu số chính là sai lầm đã biết của việc bỏ luật khỏi thang điểm làm doanh nghiệp trông sạch hơn.

### 4. Vật chứa: một doanh nghiệp, các kỳ là dòng

Màn chuẩn bị dữ liệu là **một màn cho mỗi doanh nghiệp**, liệt kê mọi kỳ thành dòng, mới nhất trước. Đầu màn là các thuộc tính mức doanh nghiệp: năm đầu nộp BCQT, niên độ, ngày quyết định kiểm tra sau thông quan — mỗi thứ sửa được tại chỗ. Khối accordion theo năm bị thay bằng bảng.

Lý do gắn với dữ liệu: cách gỡ lớp 2 trỏ tới **kỳ khác** hoặc tới **một trường của doanh nghiệp**; không cấu trúc theo kỳ đơn lẻ nào chứa được hai thứ đó.

### 5. Phản hồi nạp tại chỗ

Việc nạp không còn chuyển hướng sang trang công việc. Dòng kỳ chuyển sang trạng thái đang chạy và tự cập nhật bằng cách hỏi lại máy chủ, dùng đúng cơ chế trang tổng quan AI đang dùng. Hàng đợi chỉ chạy một việc nạp một lúc, nên dòng kỳ phải phân biệt **đang chờ** với **đang chạy**. Chẩn đoán lỗi, danh sách cột cần xác nhận và lỗi kế hoạch nạp đều hiện tại dòng kỳ, cạnh nút xử lý. Trang hàng đợi công việc vẫn còn, làm màn quản trị.

### 6. Một ô thả file cho mỗi kỳ

Trang tải lên bốn ô và ô chọn năm của nó bị bỏ. Mỗi kỳ có một ô thả nhận mọi file. Ô chọn năm không còn cần vì dòng kỳ chính là năm — điều này cũng loại bỏ khả năng nộp nhầm file của kỳ này vào kỳ khác.

### 7. Gán loại là phép gán có căn cứ

Hệ thống **gợi ý** loại cho từng file và nêu căn cứ. Ba nguồn căn cứ, mạnh→yếu: cán bộ tự chọn · đã mở file và khớp bố cục · chỉ khớp tên file. Từ **"nhận ra"** chỉ dùng cho trường hợp đã mở file; khớp tên là **gợi ý**.

Thứ tự phân giải: khớp tên trước (tức thì); file tên không phân giải được thì mới mở nội dung, và **chỉ dưới một ngưỡng kích thước**. Căn cứ đo được: mở nội dung mất khoảng 0,2 giây với biểu quyết toán nhỏ nhưng **96,9 giây** với file 71MB — và không nhận ra được BCCT trong mọi trường hợp, vì dò nội dung chỉ thử ba biểu quyết toán. File lớn không phân giải được theo tên đi thẳng vào danh sách cán bộ tự chọn.

Xác nhận thật vẫn diễn ra trong lượt nạp, nơi mọi file đều được mở.

### 8. Cổng xác nhận cột dừng lần đầu mỗi cấu trúc — HÀNH VI NÀY ĐÃ CÓ

**Đính chính.** Bản nháp trước của spec này nói cổng review dừng ở mọi lượt nạp và đề xuất nối một tham số bỏ qua. **Sai.** Đường ghi kết quả parse đã nâng các cột có map lưu khớp chữ ký cấu trúc lên mức "cán bộ đã xác nhận", nên cổng trả về rỗng và lượt nạp đi thẳng. Tham số `has_saved_map` của hàm quyết định **không có lời gọi nào trong sản phẩm** — nó là tham số chết, chỉ còn một test gọi tới.

Hệ quả: **không cần sửa gì cho hành vi lõi**, và đây **không phải** sửa đổi ADR #18. Spec chỉ ghi lại đúng hành vi đang có.

Hai điều còn mở, đã chốt:

- **Giữ nguyên khoá (doanh nghiệp, loại biểu, chữ ký cấu trúc).** Không mở rộng ra liên doanh nghiệp. Hai lý do. Thứ nhất, **chữ ký không phải định danh đầy đủ của bố cục**: chính hàm khớp mẫu từ chối trường hợp cùng chữ ký nhưng lệch dòng bắt đầu, và chữ ký gộp hoa thường, bỏ dấu, bỏ chữ số năm. Tin nhau xuyên doanh nghiệp biến một lần xác nhận sai của một cán bộ ở một doanh nghiệp thành cột đọc lệch im lặng trên cả đội — đúng dạng lỗi đã làm mất 28,5 tỷ. Thứ hai, **lợi ích gần bằng không**: bố cục thật sự dùng chung giữa các doanh nghiệp chính là bốn họ biểu đã curate sẵn, vốn đã tự qua cổng; phần map lưu còn lại là biến thể riêng của từng doanh nghiệp. Đường tin nhau xuyên doanh nghiệp **đã có sẵn và có kiểm duyệt**: khi một bố cục lặp lại ở nhiều doanh nghiệp, nâng nó thành mẫu biểu curate qua pull request kèm fixture.
- **Map cán bộ thắng mẫu biểu curate, ở mức từng trường, ngay lúc đọc file.** Trường nào map cán bộ có thì lấy vị trí của map và gắn nhãn "cán bộ đã xác nhận"; trường còn lại lấy theo mẫu biểu. Lý do: map cán bộ là sự thật kiểm chứng trên chính file của doanh nghiệp đó, mẫu biểu là suy luận cho cả đội — cán bộ đã sửa dù có mẫu khớp thì nghĩa là mẫu sai với file đó. Tài liệu của mẫu biểu **đã ghi đúng thứ tự ưu tiên này** nhưng phần cài đặt chưa tôn trọng ở mức vị trí cột. Việc này phải xong **trước khi** seed bất kỳ mẫu biểu nào có bộ cột không rỗng.

### 9. Hai màn, hai phạm vi kỳ

Màn dữ liệu (thay trang tài liệu) hiện **mọi kỳ cùng lúc**. Màn phát hiện (trang doanh nghiệp hiện tại) giữ dải tab năm và vẫn là **một kỳ một lúc**. Không gộp: gộp lại thì bộ chọn năm chỉ chi phối nửa dưới của trang. Mỗi dòng kỳ ở màn dữ liệu có đường dẫn sang màn phát hiện đúng kỳ đó sau khi đã chạy kiểm tra.

### 10. Gán sổ quyết toán ở màn thả file

Với doanh nghiệp nhiều sổ, màn thả file có thêm một ô chọn sổ cho mỗi file quyết toán, cạnh ô chọn loại. Nút nạp **khoá** khi còn file quyết toán chưa gán sổ. Ô chọn sổ vẫn sửa được sau đó trên dòng kỳ, cho file đã nằm sẵn trong hệ thống.

Điều kiện là toàn kỳ và tất-cả-hoặc-không: file quyết toán chưa gán sổ rơi vào "liên sổ", và kiểm tra đối chiếu định mức/tồn kho bên trong một cái sổ không tồn tại. Gán trước khi nạp làm lỗi kế hoạch nạp thành **không thể xảy ra** thay vì phải khắc phục sau.

Nhãn sổ trong file thô do người gõ tay nên **không** được dùng để tự nhận diện — quyết định này giữ nguyên.

### 11. Dòng kỳ mở ra: tóm tắt theo loại + danh sách file thật

Mở một dòng kỳ ra thấy hai phần:

- **Tóm tắt theo loại tài liệu** — số dòng mỗi loại. Đây là mức mà số dòng thật sự tồn tại: số dòng hiện được ghi theo loại cho cả kỳ rồi chép lên mọi file cùng loại, nên in nó cạnh từng file làm hai file tờ khai của một kỳ đọc thành tổng gấp đôi.
- **Danh sách file thật** — mỗi file một dòng, kèm các loại mà file đó phục vụ. Một workbook phục vụ ba biểu quyết toán hiện **một lần** với ba nhãn, không hiện ba lần.

### 12. Dòng file chỉ hiện thứ có hệ quả

Một nhãn chỉ xuất hiện khi nó đổi việc cán bộ phải làm: cần xác nhận cột, đọc hỏng, có cảnh báo. File bình thường hiện tên, kích thước, các loại nó phục vụ. Toàn bộ căn cứ đọc chuyển sang trang riêng của file.

**Đây là sửa đổi so với ADR #18**, vốn đặt nhãn truy nguồn ngay trên dòng để không "hộp đen" — nay truy nguồn cách một cú bấm chứ không mất.

**Ràng buộc kỹ thuật:** trường ghi "khớp mẫu bằng cách nào" hiện **không bao giờ được điền** — nó đọc một khoá mà đường đọc file hiện tại không sinh ra, nên đang rỗng trên toàn bộ file. Khối căn cứ đọc ở trang file phụ thuộc trường này; phải nối lại đường ghi, nếu không khối đó ship ra rỗng.

### 13. Đánh dấu kết quả cũ ở mọi nơi

Cơ chế so sánh phiên bản dữ liệu đã có và đang phục vụ đúng một chỗ: tổng quan AI. Mở rộng nó sang **phát hiện** và **điểm rủi ro**, đánh dấu ở dòng kỳ, ở màn phát hiện, và ở cột điểm trong bảng danh sách doanh nghiệp.

Không tự chạy lại và không giấu số. Tự chạy lại sẽ xoá rồi dựng lại phát hiện đúng ở những kỳ cán bộ nhiều khả năng đã soát. Giấu số làm doanh nghiệp rơi khỏi bảng xếp hạng — cùng dạng sai lầm với việc loại một luật khỏi thang điểm làm doanh nghiệp trông sạch hơn.

### 14. Xoá và thay file làm dời phiên bản dữ liệu

Xoá file hoặc thay file **dời phiên bản dữ liệu của kỳ**, để dấu hiệu ở mục 13 tự bật. Dòng kỳ nói rõ bộ file đã đổi còn dòng đang dùng là của bộ trước, kèm nút nạp lại. Không xoá dòng, không tự nạp lại.

Xoá theo từng file không làm được: bảng Tầng 1 không có tham chiếu về file nguồn. Nạp lại vốn đã xoá sạch (doanh nghiệp, kỳ) rồi dựng lại từ bộ file hiện tại, nên nạp lại là cách gỡ đúng.

### 15. Kỳ báo cáo và ba cảnh báo của nó

Cửa sổ kỳ hiện trên dòng kỳ **chỉ khi khác năm dương lịch**, sửa được tại chỗ. Ba khối cảnh báo hiện nay — khoảng thiếu dòng tờ khai, dòng lệch cửa sổ kỳ, kỳ chồng lấn — thôi làm khối riêng và trở thành mục trong danh sách vướng mắc ở mục 2: khoảng thiếu là "nạp thêm file kỳ khác", lệch cửa sổ là "soát lại file nguồn", chồng lấn là "sửa cửa sổ kỳ".

Đo được: trên 15 kỳ, khoảng thiếu bắn ở 2, chồng lấn 0, lệch cửa sổ 0 trên dữ liệu thật.

### 16. Xem trước file thành lưới cuộn được

Bỏ cả ba hạn mức hiện tại: 100 dòng, 40 cột, 25MB. Máy chủ trả một cửa sổ ô dạng JSON; trình duyệt dựng lưới cuộn ảo với số dòng và chữ cái cột dính mép, cuộn được cả hai chiều, nhảy được tới một dòng cụ thể.

**Trích xuất một lần, không đọc thẳng từ workbook mỗi cửa sổ.** Lần đầu mở lưới của một trang tính, hệ thống đọc trọn trang đó một lượt vào một **kho đệm SQLite riêng cho mỗi (file, trang tính)**; mọi cửa sổ sau là một truy vấn khoảng dòng.

Lý do là số đo: mở file 71,3MB ở chế độ đọc tuần tự chỉ mất **1,19 giây** — hạn mức 25MB hiện nay là hệ quả của việc đọc trọn trang tính bằng thư viện bảng dữ liệu, không phải chi phí mở file. Nhưng chế độ đó **chỉ đi tới**, và nhảy tới dòng 200.000 mất **3,87 giây**. Cuộn từ đầu tới cuối một trang 270.000 dòng theo cửa sổ 200 dòng là khoảng một nghìn lượt đọc với chi phí tăng dần — không dùng được. Trích xuất trả chi phí đó **đúng một lần**, đổi lại nhảy tới dòng bất kỳ là tức thì, vốn là yêu cầu của người dùng ở mục 33.

- Kho đệm ghi **theo dòng**: khoá `(chỉ số trang tính, chỉ số dòng)`, giá trị là một mảng JSON mỗi dòng, công thức là một từ điển thưa `{cột: công thức}` mỗi dòng. Ghi theo ô sẽ thành 270.000 × số cột lượt ghi với trang 257 cột.
- Dựng **ngay trong request đầu tiên**, sau một khoá chống dựng trùng (ghi file tạm rồi đổi tên nguyên tử). **Không** đẩy vào hàng đợi: hàng đợi chạy một việc một lúc, nên một việc trích xuất xếp sau một lượt nạp dài làm cán bộ chờ vài phút chỉ để xem file.
- Thư mục kho đệm nằm ngoài thư mục dữ liệu thật (thư mục đó là liên kết tới dữ liệu khách) và không commit. Khoá vô hiệu hoá theo `(đường dẫn, thời điểm sửa, kích thước, trang tính)` — cùng quy tắc bộ nhớ đệm parse đang dùng. Có giới hạn dung lượng và dọn theo ít dùng nhất.
- Số dòng và số cột tổng lấy **từ kết quả trích xuất**, không lấy từ khai báo kích thước trong file: file kết xuất khai sai kích thước, mà thanh cuộn ảo cần số thật.

**Ba bộ đọc, nhận dạng theo NỘI DUNG chứ không theo đuôi file.** Đuôi file nói dối — 38 file mang đuôi `.xls` thật ra là XML. Nhận theo byte đầu: `PK` → xlsx đọc tuần tự · `D0CF` → xls BIFF · `<?xml` → XML SpreadsheetML đọc bằng thư viện XML chuẩn. File không khớp dạng nào hiện thẻ lỗi **nêu đúng định dạng dò được**, không nhắc lại cái đuôi sai.

XML SpreadsheetML được hỗ trợ, không từ chối. Đo trên file lớn nhất nhóm này (64,5MB): đọc trọn bằng thư viện chuẩn mất **3,49 giây** cho 12.749 dòng — định dạng này cồng kềnh chứ dữ liệu không lớn, nên trích xuất ngay trong request là thoải mái. Định dạng này lưu công thức ngay cạnh giá trị, nên 38 file đó có đủ cả hai công tắc.

**Một chỗ giảm chất lượng có chủ ý, phải nói rõ:** file `.xls` cũ **không đọc được công thức** — thư viện đọc định dạng đó chỉ trả về giá trị đã tính và không phân biệt được ô nào là công thức. Công tắc "hiện công thức trong ô" với file `.xls` hiện dòng chữ nói đúng như vậy, **không** hiện lưới rỗng.

**Phạm vi:** 38 file XML kia **xem trước được nhưng chưa nạp được** — bộ đọc dữ liệu không đổi trong spec này. Trang file phải ghi rõ trạng thái nửa vời đó chứ không để cán bộ tự đoán.

Hai công tắc trên lưới:

- **"Hiện cột hệ thống đang đọc"** — đánh dấu mỗi cột parser thật sự đọc và gắn nhãn trường nó được đọc thành. Cơ chế này đã có ở màn xác nhận cột, chỉ chuyển sang lưới mới.
- **"Hiện công thức trong ô"** — hiện nội dung gốc trong ô thay vì giá trị hiển thị. Có mặt vì một bộ file từng chứa hơn hai nghìn ô lưu dạng công thức mà bộ đọc trả về 0, làm mất 28,5 tỷ mà không kiểm tra nào bắt được.

**Phụ thuộc mới:** một thư viện lưới JavaScript. Dự án **không có** bộ đóng gói frontend và toàn bộ script hiện tại là JavaScript thuần viết tay, nên thư viện phải nhúng thành **một file tĩnh duy nhất**, không thêm bước build, không thêm quản lý gói.

### 17. Một trang cho mỗi file

Trang xem file và trang xác nhận cột nhập làm một, tại địa chỉ theo mã file: lưới cuộn, hai công tắc, biểu mẫu xác nhận vị trí cột, ô chọn sổ, và khối căn cứ đọc từ mục 12. Hai địa chỉ cũ chuyển hướng về đây.

Địa chỉ trang tải lên cũ: phương thức GET chuyển hướng về màn dữ liệu của doanh nghiệp (bốn liên kết trong giao diện đang trỏ tới nó); phương thức POST trở thành đích nhận file của ô thả.

## Testing Decisions

Một test tốt ở đây kiểm **hành vi quan sát được từ bên ngoài**: mã trạng thái và dữ liệu trang trả về, dòng đã ghi vào DB, và giá trị hàm phân loại trả về. Không kiểm cấu trúc nội bộ, không kiểm tên biến.

**Không khoá test vào chuỗi tiếng Việt trên giao diện.** Đây là điểm quan trọng nhất của mục này: khoảng một chục bộ test hiện có khẳng định bằng cách dò chuỗi tiếng Việt trong HTML. Spec này viết lại phần lớn các template đó, nên chuỗi sẽ đổi — và kiểu test đó **vẫn xanh trong khi thôi kiểm đúng thứ nó tuyên bố kiểm**. Mọi thứ kiểm được ở mức dữ liệu (hàm thuần hoặc JSON) phải kiểm ở đó; chỉ khẳng định trên markup khi chính thuộc tính markup là hành vi.

### Bốn seam

**Seam 1 — tầng HTTP kèm chạy hàng đợi (đã có, chính).** Máy khách test trên ứng dụng, thư mục dữ liệu thô trỏ vào thư mục tạm, file sinh trong test, rồi chạy hết job đã xếp bằng tiện ích sẵn có. Phủ: thả file → gợi ý loại → job nạp → dòng kỳ, xoá/thay file, khoá nút nạp khi thiếu sổ, chuyển hướng địa chỉ cũ.

**Seam 2 — hàm thuần trên phiên DB (đã có).** Hàm đếm "đủ dữ liệu" và hàm phân loại vướng mắc theo cách gỡ. Bắt buộc: hàm nhận phiên DB làm tham số và **không được tự mở phiên nào bên trong** — mở phiên bên trong là đọc trúng DB dev của máy.

**Seam 3 — bộ đọc cửa sổ ô (mới).** Hàm nhận (đường dẫn, trang tính, dòng bắt đầu, số dòng, cột bắt đầu, số cột) trả về ô. Ba ca **bắt buộc**, mỗi ca ứng với một dạng hỏng đã từng xảy ra: ô công thức (bộ đọc cấu hình sai thì hiện `=SUM(...)` thay vì số, hoặc ngược lại nuốt mất công thức — đúng dạng lỗi làm mất 28,5 tỷ); trang tính 257 cột; và cả ba định dạng file thật (xlsx nén, xls BIFF, XML SpreadsheetML mang đuôi `.xls`).

**Seam 4 — gọi thẳng hàm route trạng thái nạp (mới, rẻ).** Cần vì tiện ích chạy hàng đợi chạy job đến hết trong một lần gọi, nên **không test nào viết theo seam 1 quan sát được trạng thái đang chờ hay đang chạy** — mà đó chính là hành vi mục 5 thêm vào. Dựng sẵn bản ghi công việc ở từng trạng thái (chờ, đang chạy, xong, hỏng) cộng hai dạng kết quả `plan_error` và `needs_review`, gọi thẳng hàm route và khẳng định trên dữ liệu trả về. Kèm ca **công việc mồ côi**: tiến trình chết giữa chừng để lại bản ghi "đang chạy" vĩnh viễn, mà việc dọn chỉ chạy lúc khởi động — không có đường lùi thì bảng điều khiển quay mãi. Tiền lệ: bộ test tổng quan AI bất đồng bộ gọi hàm route trực tiếp theo đúng cách này.

### Test giá trị cao nhất: bảng điều khiển phải khớp trạng thái đã lưu

Con số "đủ dữ liệu cho N/M" tính trước khi chạy kiểm tra, còn lớp cách gỡ đã lưu sinh ra lúc chạy. Hai đường này **có thể lệch nhau**, và có sẵn ba ca lệch để kiểm: kiểm tra khai cần "BCCT **hoặc** M16" mà bộ khai điều kiện không diễn đạt được phép hoặc; kiểm tra đọc M15 của **kỳ trước**; cổng định mức phụ thuộc định mức hiệu lực xuyên kỳ. Test: chạy trọn pipeline rồi khẳng định lớp bảng điều khiển dự đoán cho mỗi mã **bằng** lớp đã lưu cùng lần chạy. Lệch thì hoặc sửa dự đoán, hoặc bảng điều khiển phải nói rõ là nó không dự đoán được mã đó.

### Không phải seam

Lưới JavaScript. Không có bộ công cụ test JS trong repo. Nghiệm thu bằng quy ước ảnh E2E sẵn có: kịch bản Playwright đặt cạnh brief trong thư mục tính năng, ảnh ghi vào thư mục con của chính nó.

### Bẫy DB dev — bắt buộc sửa trước khi viết test mới

Test trong repo xanh giả vì bám DB dev của máy, và cách vá hiện tại **chưa đủ cho tính năng này**. Module nạp dữ liệu lấy phiên DB bằng `from ... import` ở mức module, tức vá biến của module DB **không** đổi được nó; module route thì lại phân giải lúc gọi nên vá được. Hệ quả cụ thể: bộ test form tải lên — thứ gần nhất với việc cần làm — an toàn **chỉ vì nó không bao giờ chạy job**. Test thả file nào sao chép cách dựng đó rồi chạy job sẽ ghi dòng Tầng 1 và bản ghi doanh nghiệp vào **DB thật của máy dev**, và khẳng định kiểu "không có dòng nào vì chưa gán sổ" sẽ xanh vì lý do sai.

Bắt buộc: **một fixture dùng chung** vá cả ba điểm (engine, phiên ở module DB, phiên đã import vào module nạp), thay vì bản sao thứ 21 của khối dựng cũ. Quy tắc cho code mới: module mới **không** được `from ... import` phiên DB ở mức module.

### Bất biến phải chuyển chỗ, không được mất

Bộ test form tải lên hiện khẳng định thuộc tính `multiple` trên ô BCCT bằng cách đọc thẳng markup — vì thiếu thuộc tính đó thì trình duyệt chỉ gửi một file và mọi sửa đổi phía máy chủ thành vô ích. Trang đó biến mất theo mục 6, nhưng **bất biến vẫn còn**: ô thả phải nhận được nhiều file. Phải khẳng định lại trên ô thả mới.

### Hai tầng chặn của việc gán sổ

Mục 10 chặn ngay ở màn thả file. Lỗi kế hoạch nạp phía dưới **giữ nguyên làm lớp chặn cuối** và phải test cả hai tầng — chặn sớm để cán bộ không phải chờ, chặn muộn để đường nạp bằng dòng lệnh và mọi đường khác vẫn an toàn.

## Out of Scope

- **Màn phát hiện không bị viết lại.** Dải tab năm giữ nguyên, cách hiển thị phát hiện giữ nguyên. Chỉ thêm dấu hiệu kết quả cũ và đường dẫn qua lại với màn dữ liệu.
- **Không đổi logic kiểm tra nào.** Không đổi ngưỡng, không đổi công thức, không thêm bớt kiểm tra.
- **Thang điểm rủi ro không đụng tới.** Vấn đề trần điểm và ảnh hưởng của trạng thái chưa đánh giá được lên điểm là việc riêng, đang mở ở issue khác.
- **Chạy lại kiểm tra vẫn xoá trạng thái cán bộ đã đánh trên phát hiện.** Việc chạy lại xoá rồi dựng lại dòng phát hiện, đưa trạng thái và ghi chú của cán bộ về "mới". Hiện chưa lộ vì chưa ai dùng tính năng đánh dấu, nhưng sẽ lộ ngay khi thí điểm bắt đầu. Đây là lý do spec này **không** tự chạy lại kiểm tra sau khi nạp — nhưng sửa nó nằm ngoài phạm vi.
- **Tự nhận diện sổ quyết toán từ nội dung file.** Đã có quyết định không đọc nhãn sổ trong file thô.
- **Tải lên theo mảnh cho file rất lớn.** Thời gian truyền file 68MB là một mặt trận khác.
- **Anonymize và đường dữ liệu demo.**

## Further Notes

### Một sửa đổi ADR phải ghi lại

Chỉ **mục 12** đảo lại lập trường của ADR #18 — việc đặt nhãn truy nguồn ngay trên dòng file. Mục 8 hoá ra **không** phải sửa đổi: hành vi mong muốn đã có sẵn, xem đính chính ở mục đó. Số ADR tiếp theo là **#24**, nối tiếp dãy số toàn cục.

### Ba định dạng file, không phải một

Đếm trên toàn bộ 493 file trong thư mục dữ liệu thật:

| Đuôi | Định dạng thật | Số file | Dung lượng | Lớn nhất |
|---|---|---|---|---|
| `.xlsx` | zip (xlsx thật) | 268 | 267,0 MB | 71,3 MB |
| `.xls` | BIFF/OLE2 (xls thật) | 185 | 288,5 MB | 39,3 MB |
| `.xls` | **XML SpreadsheetML** | **38** | **190,8 MB** | 64,5 MB |
| `.xlsx` | hỏng / rỗng | 2 | ~0 | — |

38 file mang đuôi `.xls` nhưng thật ra là XML: không thư viện đọc Excel nào trong dự án mở được chúng. Con số này khớp ghi chú sẵn có trong mã nguồn về "40 file không mở được" — tức **7,7% kho dữ liệu và 190 MB hiện không đọc được**, và mọi mục của spec này chạm tới việc đọc file đều phải khai rõ hành vi với nhóm đó.

### Bảng điều khiển đang đo sai thứ

Phép đếm "đủ dữ liệu" đọc **dòng đã nạp**, không đọc **file đã có**. Hai hệ quả đã xác minh:

- Lượt nạp dừng ở cổng xác nhận cột ghi **không dòng nào**, trong khi file đã nằm trên đĩa và đã đăng ký. Bảng điều khiển sẽ báo thiếu nguồn và bảo cán bộ "nạp thêm file kỳ này" — việc họ vừa làm xong.
- Xoá file **không xoá dòng đã nạp**, nên bảng điều khiển vẫn báo "đủ" sau khi file đã biến mất.

Nghĩa là cần một trạng thái thứ ba giữa "chưa có file" và "đã có dòng": **đã có file, chưa nạp được dòng**. Trạng thái đó đã tồn tại trên bản ghi file. Cách xử lý chốt ở vé nền tảng, trước khi dựng màn hình.

### Trạng thái cần dọn trước khi dùng được

Doanh nghiệp nhiều sổ hiện **không nạp lại được qua web**: dòng Tầng 1 của nó mang nhãn sổ trong khi không file nào mang nhãn, nên kế hoạch nạp bị từ chối. Mục 10 sửa đường đi cho lần sau; **dòng file đang có vẫn phải gán lại sổ** thì doanh nghiệp đó mới nạp được. Đây là việc dọn dữ liệu, cần một vé riêng.

### Trường "khớp mẫu bằng cách nào" đang rỗng

Nêu lại vì dễ mất: khối căn cứ đọc ở trang file đọc một trường hiện không bao giờ được điền. Không nối lại đường ghi thì khối đó ship ra rỗng và mục 12 mất phần bù cho việc bỏ nhãn khỏi dòng file.

### Số đo dùng làm nền cho spec này

Đo trên DB dev và thư mục dữ liệu thật ngày 07/08/2026:

- 10 lần "chưa đánh giá được" của một kiểm tra: 1 gỡ bằng file kỳ này, 6 cần kỳ khác hoặc xác nhận, 3 không gỡ được.
- Năm đầu nộp BCQT rỗng trên **toàn bộ 7 doanh nghiệp**; ngày quyết định kiểm tra sau thông quan cũng rỗng cả 7, nên màn phạm vi 5 năm hiện trả về không tìm thấy cho mọi doanh nghiệp.
- 52/170 trang tính đo được vượt 40 cột, rộng nhất 257 cột.
- 11/493 file Excel vượt 25MB.
- Mở nội dung để đoán loại: 0,14–0,20 giây với biểu nhỏ, 96,93 giây với file 71,3MB và không nhận ra được gì vì đó là BCCT.
- Số dòng ghi theo loại rồi chép lên mọi file cùng loại: hai file tờ khai của một kỳ cùng mang 270.505, trong khi cả kỳ có đúng 270.505 dòng.
- Trường "khớp mẫu bằng cách nào" rỗng trên 15/15 file; nhãn review có trên 4/15, đều là "đã kiểm".
- 15 kỳ: khoảng thiếu dòng tờ khai bắn ở 2, chồng lấn 0, lệch cửa sổ 0.
- Mọi kỳ hiện đồng bộ giữa phiên bản dữ liệu và phiên bản lần chạy kiểm tra, nên chưa có kỳ nào đang ở trạng thái cũ để quan sát.
