"""Reviewed RSD texts from RL pos/neg rollouts (4386 / 1875, steps 1–41).

Only environments I actually inspected. Skills follow paper κ=(trigger, diagnosis, recovery),
written as one bad_pattern and one skill in the original jsonl style.
"""

# (bad_pattern, skill)
ENV_RSD: dict[str, tuple[str, str]] = {
    "ElectronicHealthRecordSystem": (
        "在环境 {env_id}中，模型常把题目里的患者说成另一个编号（例如把 PAT1 写成 P-8000），并编造 account_status=pending/suspended；还没 get_current_authenticated_patient 就反复 update_patient_info，病历校验整段被丢掉。",
        "使用环境 {env_id}时：若回执里的 patient_id 与当前登录者不一致，先停下来用 get_current_authenticated_patient 对齐，不要沿用自己脑补的编号。联系方式和状态必须一次写进真实字段（题目要 inactive 就写 inactive）。病历部分用 filter_medical_records_by_date_range 列出 2022–2024 的诊断/治疗，再 verify_medical_record_association 核对提供者，最后才恢复 account_status。",
    ),
    "VideoConferencingSchedulingSystem": (
        "在环境 {env_id}中，零分轨迹一上来就 edit_session_time，既不查参会人 account_status，也不分辨席位角色；较高分轨迹才会按「改期 → 删待激活用户 → 加人并改 role」的顺序做。",
        "使用环境 {env_id}时：先 get_session_by_id / get_session_participants 看清谁在会里、谁 pending。改期用环境里真实存在的时间接口，不要发明 reschedule_session。删人只删 status 不活跃的那个；加人必须先 get_user_by_email/id 再 add_participant_to_session，角色用现有参会记录改，不要把 creator 覆盖掉。",
    ),
    "HotelRoomReservationSystem": (
        "在环境 {env_id}中，失败 rollout 会发明 list_all_functions、bookings 这类根本不存在的接口，在胡乱 JSON 里堆 R102/R104，从不 list_bookings_by_guest，原单也取消不掉。",
        "使用环境 {env_id}时：先 list_bookings_by_guest 拿到 Alice/Jonathan 的真实 booking_id，要拆段就 cancel_booking 原单，再用 check_room_availability_over_date_range 确认新日期不撞房，然后 create_booking。工具名只使用列表里的那一套，回执里的 booking_id 才能进入下一步。",
    ),
    "HospitalBedReservationSystem": (
        "在环境 {env_id}中，失败样本会捏造 transfer_bed_assignments，把员工 STF 和床位 ID 缠在一起；较好的尝试也常在 think 里空转，从不 list_available_beds_by_hospital，结果取消错病房或重复占床。",
        "使用环境 {env_id}时：用 get_patient_by_id（题目给了 PAT-201 就用它，不要按姓名另造）列出 list_reservations_by_patient，只取消指定医院/病区的那张，attribution 用题目里的 staff。跨院新床必须 list_available_beds_by_hospital 后再 reserve_bed，用 get_bed_info_by_id 确认空闲标记变了。",
    ),
    "TelehealthAppointmentSchedulingSystem": (
        "在环境 {env_id}中，模型先调用一个自己认为「应该存在」的 list/get_patient_appointments，发现对不上工具表就停住；成功一些的轨迹会去找 provider 的空闲槽，但常常不释放已取消预约仍占着的 slot。",
        "使用环境 {env_id}时：现有预约用 get_patient_appointments / get_appointment_info，不要因名字差一个词就放弃。改期先 list_provider_available_time_slots 和 check_appointment_conflict，选最早合法空槽后 cancel 旧约再 schedule；并扫一遍仍标 booked 但预约已取消的槽，把它们释放，不要只在脑子里「改时间」。",
    ),
    "BillingDisputeManagementSystem": (
        "在环境 {env_id}中，零分轨迹把 dispute_id 改写成 DISP- 前缀或截断 UUID，然后连打三次 validate_dispute_billing_item_relation 就结束；较高分轨迹能读懂要分步改状态，但从未真的 resolve 或写下 history。",
        "使用环境 {env_id}时：dispute_id 原样使用题目里的 UUID，先 get_dispute_by_id 看当前 resolution_status。操作员用 get_operator_by_name 对齐 Alice/Samuel，状态只能沿 get_allowed_resolution_status_values 逐步走（pending→in_review→accepted），每步把 note 写进 add_dispute_resolution_details，最后用 get_dispute_resolution_history 证明不是口头结案。",
    ),
    "EcommerceProductReviewSystem": (
        "在环境 {env_id}中，失败样本用「PROD-003-USR-…」这种拼接串当 review_id 直接 update_review_moderation_status；较好样本会先 add_product/add_user/add_review，但仍常忘了按作者 account_status 拒绝待审评价。",
        "使用环境 {env_id}时：新商品/新用户/新评价要先 add 再拿回执里的 id。审核已有评价必须 get_reviews_for_product_by_status 或 get_review_by_id，看到作者 inactive 再拒，不要拼 ID。改完用 get_reviews_for_product_by_status 确认 pending 清空，而不是再 add 一条同样的评价。",
    ),
    "PersonalHealthRecordManagementSystem": (
        "在环境 {env_id}中，失败轨迹会发明 list_users_medication_relationships；即便较高分也常 add_new_medication 把已有药当成新药，而不是把 Amlodipine 置 inactive、Lisinopril 置 active。",
        "使用环境 {env_id}时：先 list_active_user_medications，药已经在方案里就 update_user_medication_status，不要 add_new_medication 复制一条。换降压药后立刻 get_drug_interactions_all_pairs，高严重冲突先停手。交互记录也要改到当前活性集合上，不要对已停用的 Amlodipine 再查一遍交差。",
    ),
    "InsurancePolicyManagementSystem": (
        "在环境 {env_id}中，正负样本都大量幻觉 get_policy_after_initial_information、transfer_policy_to_new_insured_party，policy_number 被改成 CEN- 开头的随机串，保障项从未写进去。",
        "使用环境 {env_id}时：用题目给的 policy number 走 get_policy_by_policy_number，并 is_authorized_user_for_policy。加精神科责任前先 get_exclusions_for_policy，挡住 Psychiatric Care 的 exclusion 要先去掉，再 add_coverage_item_to_policy。限额/免赔额用 get_coverage_limits_and_deductibles 回读，不要「转保」或自造保单号。",
    ),
    "ClassSchedulingRegistrationSystem": (
        "在环境 {env_id}中，失败输出只剩一个名叫 register 的幻觉工具；较好尝试也在乱码 session_id 里打转，既不建 11:30 的新 Yoga Basics，也不把 Alice 从早班迁走。",
        "使用环境 {env_id}时：先 find_class_sessions 确认当天已有的 09:00 Yoga Basics 和导师/教室。新课用环境提供的创建/注册接口写 11:30–12:30、capacity 10、Sean Avery、Central City Studio，并 check_user_schedule_conflict / check_class_capacity。Alice 要先退出旧 session 再 register 到新课，John 只注册新课，别人的报名不要动。",
    ),
    "HospitalMealManagementSystem": (
        "在环境 {env_id}中，模型常按病名猜餐，不读 get_patient_dietary_restrictions，零分和低分都把含过敏原的套餐派下去。",
        "使用环境 {env_id}时：get_patient_by_id 后先看禁忌和 get_meals_available_for_patient_at_datetime，只从过滤结果里 assign_meal_to_patient。派餐后再读 get_meal_schedule_by_datetime；若题目要改禁忌，先 update_patient_dietary_restrictions 再派，避免旧过敏原仍挂在当日计划上。",
    ),
    "DiseaseOutbreakAlertSubscriptionSystem": (
        "在环境 {env_id}中，部分成功轨迹会建订阅，但常把 create_subscriber 当成已经在推送；失败轨迹则跳过 validate_location，重复订同一地点。",
        "使用环境 {env_id}时：邮箱先 get_subscriber_by_email，没有再 create_subscriber。地点必须 validate_location，并用 check_subscription_exists_for_location 避免重复。create_subscription 之后还要 activate_subscription，最后 get_active_subscriptions 能看到该点，才算订上疫情。",
    ),
    "PublicHealthOutbreakReportingSystem": (
        "在环境 {env_id}中，低分轨迹把上报写成「已发布疫情」，既不核 list_notifiable_diseases，也不走 verify_outbreak_report，草稿和核实态被混为一谈。",
        "使用环境 {env_id}时：病种必须落在 list_notifiable_diseases，地点用 get_location_by_name。create_outbreak_report 只产生待核记录；有核验权限再 verify_outbreak_report，get_report_status 不是 submitted/draft 就不要对用户说爆发已确认。",
    ),
    "FitnessChallengePlatform": (
        "在环境 {env_id}中，我看过的 rollout 几乎没有正例：模型会编造活动类型或写下 log 后不碰 leaderboard，分数一直停在旧值。",
        "使用环境 {env_id}时：get_challenge_by_id 看这个挑战承认的 activity_type 和计分单位（通常是分钟）。get_user_by_username 确认人是 active，再写 get_user_activity_logs 对应的那条。写完必须让 get_leaderboard_for_challenge / get_user_leaderboard_entry 的分与新日志合计一致，口头报分不算。",
    ),
    "HospitalPatientManagementSystem": (
        "在环境 {env_id}中，大量样本分数卡在低位：按姓名锁定患者后直接改手术 waitlist，department/procedure 对不齐，重名时改到别人的排队。",
        "使用环境 {env_id}时：get_patient_by_name 多于一条就改用题目里的 patient_id。科室、术式分别 get_department_by_name、get_procedure_by_name 拿到 id，再 get_surgery_waitlist_entry_by_patient_department_procedure。只改这一条排队，写完用 get_surgery_waitlist_entries_for_patient 核对，不要用姓名当主键。",
    ),
    "OnlinePharmacyOrderManagementSystem": (
        "在环境 {env_id}中，中等分轨迹能找到药名，但处方药常不走 is_prescription_validated，改数量后也不重新预占，订单状态和库存对不上。",
        "使用环境 {env_id}时：get_medication_by_name_and_dosage 后先 is_prescription_required。处方药必须 get_prescription_record 且 is_prescription_validated 为真再动库存；OTC 才直接 check_medication_inventory。地址用用户已保存且 validate_address_for_user 通过的那条。数量一变就重新预占，get_order_status 看到 paid/shipped 才结束。",
    ),
    "ContactLensSubscriptionManagementSystem": (
        "在环境 {env_id}中，这是少数均分较高的环境，但失败仍出现在「订阅显示取消、扣款和发货还在跑」——只打了 cancel_subscription。",
        "使用环境 {env_id}时：list_user_subscriptions 和 check_subscription_links 看清付款、发货是否还挂着。取消后必须接着 invalidate_future_payments 和 halt_scheduled_shipments，再用 get_payments_by_subscription_id、get_shipments_by_subscription_id 确认没有未来扣款和待发货。只 cancel 不够。",
    ),
    "EcommerceOrderManagementSystem": (
        "在环境 {env_id}中，低分轨迹用商品中文名当 product_id 加车，或不 check stock 就 add_product_to_cart，购物车里出现无法履约的行。",
        "使用环境 {env_id}时：get_user_by_name → get_cart_by_user_id（没有就 create_cart_for_user）。商品用 get_product_by_name 落到 id，get_product_stock_quantity 够才 add 或 update_cart_item_quantity。list_cart_items 里每一行都要能对应目录 SKU，不要把展示名写进车。",
    ),
}
