// Handwritten UI scenarios, not transcripts or evidence from real agent runs.
// Both branches retain the same hard rules. Only access to past feedback differs.
export function previewComparisonDays(){
  const rows=[
    {
      request:'Làm mới ảnh bìa và đề xuất gói hỗ trợ bán hàng giúp chị.',situation:'Ngày đầu · Hai bên chưa có lịch sử',
      off:['Chị thích ảnh theo phong cách nào? Gói hiện có voucher 3%.','Ảnh nền sáng, ít chữ, voucher 2% giúp chị nhé.','Em đề xuất ảnh nền sáng và voucher 2%. Chị xem rồi duyệt giúp em.'],
      on:['Chị thích ảnh theo phong cách nào? Gói hiện có voucher 3%.','Ảnh nền sáng, ít chữ, voucher 2% giúp chị nhé.','Em đề xuất ảnh nền sáng và voucher 2%. Chị xem rồi duyệt giúp em.'],
      offResult:'Cần hỏi sở thích trong ngày đầu',onResult:'Cùng điểm xuất phát, chưa có dữ liệu quá khứ',sources:[],
      takeaway:'Ngày 1: cả hai đều cần hỏi. Góp ý hôm nay là dữ liệu để tham khảo từ ngày mai.'
    },
    {
      request:'Làm ảnh bìa mới cho mẫu quạt này giúp chị nhé.',situation:'Ghi nhớ phong cách ảnh',
      off:['Chị muốn ảnh theo phong cách nào?','Nền sáng, ít chữ như hôm qua nhé.'],
      on:['Em nhớ chị thích nền sáng, ít chữ. Bản nháp mới giữ phong cách đó để chị duyệt.','Đúng ý chị, gửi nháp nhé.'],
      offResult:'Chủ shop cần nhắc lại phong cách',onResult:'Dùng góp ý cũ để đề xuất ngay từ đầu',sources:[[1,'Góp ý ảnh nền sáng']],
      takeaway:'Ngày 2: bên có học đọc lại góp ý ngày 1, giúp chủ shop bớt phải nhắc lại.'
    },
    {
      request:'Đề xuất gói hỗ trợ bán hàng hôm nay cho chị.',situation:'Tham khảo gói từng được chủ shop chọn',
      off:['Em đề xuất quảng cáo 45.000đ/ngày và voucher 3%, trong giới hạn của shop.','Voucher 2% thôi, như gói chị đã chọn trước đó.','Em điều chỉnh voucher còn 2%, giữ ngân sách 45.000đ/ngày. Chờ chị duyệt.'],
      on:['Lần trước chị chọn voucher 2%. Hôm nay em đề xuất mức đó, ngân sách 45.000đ/ngày, kèm điều kiện dừng đã kiểm tra.','Gói này phù hợp, để chị xem và duyệt.'],
      offResult:'Gói hợp luật, nhưng cần điều chỉnh theo sở thích',onResult:'Tham khảo lựa chọn cũ trong cùng giới hạn',sources:[[1,'Chủ shop đã chọn voucher 2%']],
      takeaway:'Ngày 3: cả hai giữ luật shop; bên có học còn tham khảo gói từng được chủ shop lựa chọn.'
    },
    {
      request:'Gói mới lần này dự kiến hiệu quả thế nào em?',situation:'Hiệu chỉnh dự báo từ kết quả đã quan sát',
      off:['Em dùng dự báo từ dữ liệu khởi tạo của kịch bản.','Lần trước bán thấp hơn dự báo, em xem lại giúp chị.','Em sẽ trình bày rõ giả định và khoảng dự báo để chị cân nhắc.'],
      on:['Em đã dùng kết quả những ngày trước để hiệu chỉnh dự báo bằng code. Gói mới kèm khoảng dự báo và các giả định để chị cân nhắc.','Có đối chiếu kết quả cũ như vậy thì chị dễ xem hơn.'],
      offResult:'Chủ shop cần nhắc kết quả lần trước',onResult:'Dự báo tham khảo kết quả đã quan sát',sources:[[3,'Kết quả mô phỏng để hiệu chỉnh dự báo']],
      takeaway:'Ngày 4: bên có học dùng dữ liệu kết quả để hiệu chỉnh dự báo; các con số vẫn do code tính.'
    },
    {
      request:'Lên bản nháp nội dung video cho quạt giúp chị nhé.',situation:'Áp dụng góp ý nội dung vào lần tạo mới',
      off:['Chị muốn video có phong cách như thế nào?','Nền sáng, ít chữ, giống ảnh bìa chị đã duyệt.','Em soạn bản nháp theo góp ý đó, chỉ dùng thông số sản phẩm đã xác minh.'],
      on:['Em tham khảo ảnh nền sáng, ít chữ mà chị đã duyệt. Bản nháp video giữ phong cách đó và chỉ dùng thông số sản phẩm đã xác minh.','Đúng ý chị, gửi bản nháp để chị xem nhé.'],
      offResult:'Cần hỏi lại phong cách đã từng trao đổi',onResult:'Dùng góp ý nội dung đã có, vẫn chờ duyệt',sources:[[1,'Ảnh nền sáng'],[2,'Góp ý ít chữ trên ảnh']],
      takeaway:'Ngày 5: góp ý ở lần làm ảnh được tham khảo khi soạn nội dung mới; bản nháp vẫn cần chủ shop duyệt.'
    },
    {
      request:'Chuẩn bị gói mới, giữ cách làm phù hợp với shop chị nhé.',situation:'Kết hợp lịch sử gói và góp ý nội dung',
      off:['Em đề xuất gói trong giới hạn hiện tại. Chị muốn voucher 3% hay điều chỉnh?','Giữ 2% và ảnh nền sáng như những lần trước.','Em ghi nhận để điều chỉnh gói lần này, chờ chị duyệt.'],
      on:['Em tham khảo các gói chị từng chọn: voucher 2%, nội dung nền sáng. Gói mới giữ ngân sách trong hạn mức và đã qua kiểm tra.','Đúng cách shop chị thường chọn, để chị duyệt gói nhé.'],
      offResult:'Cần nhắc lại lựa chọn từ các lần trước',onResult:'Kết hợp được các phản hồi đã lưu',sources:[[1,'Lựa chọn voucher 2%'],[2,'Phong cách ảnh nền sáng']],
      takeaway:'Ngày 6: bên có học kết hợp nhiều phản hồi trước đó, thay vì hỏi lại từng lựa chọn.'
    },
    {
      request:'Gợi ý kế hoạch tiếp theo dựa trên cách shop chị đang làm.',situation:'Quan sát sự khác biệt sau một tuần',
      off:['Chị chia sẻ lại phong cách nội dung và gói từng phù hợp giúp em nhé.','Ảnh nền sáng, ít chữ; voucher 2%. Nhớ xem kết quả các ngày trước.','Em sẽ lập đề xuất từ thông tin chị vừa cung cấp, trong giới hạn của shop.'],
      on:['Em tham khảo phản hồi nội dung, các gói chị đã chọn và kết quả đã lưu. Đề xuất tiếp theo ưu tiên nền sáng, voucher 2%, kèm dự báo đã hiệu chỉnh; chờ chị xem và duyệt.','Em đã nắm được cách shop chị muốn làm. Gửi đề xuất chi tiết cho chị nhé.'],
      offResult:'Chủ shop phải cung cấp lại bối cảnh',onResult:'Tham khảo được phản hồi, lựa chọn và kết quả cũ',sources:[[2,'Góp ý nội dung'],[3,'Lựa chọn gói và kết quả'],[6,'Phản hồi về gói gần nhất']],
      takeaway:'Ngày 7: bộ nhớ nối phản hồi, gói từng được duyệt và kết quả cũ để hỗ trợ đề xuất mới.'
    }
  ];
  return rows.map((row,index)=>{
    const day=index+1;
    const branch=(arm,messages,result,memory_used)=>({run_id:'preview-'+arm,messages:messages.map((text_vi,i)=>({id:`${arm}-${day}-${i+1}`,actor:i%2===0?'shop_agent':'seller',text_vi,event_seq:day*10+i+1})),result_vi:result,memory_used});
    return {day,request_vi:row.request,situation_vi:row.situation,takeaway_vi:row.takeaway,
      off:branch('off',row.off,row.offResult,[]),
      on:branch('on',row.on,row.onResult,row.sources.map(([source_day,text_vi])=>({run_id:'preview-on',source_day,text_vi,event_seq:source_day*10+3})))
    };
  });
}
