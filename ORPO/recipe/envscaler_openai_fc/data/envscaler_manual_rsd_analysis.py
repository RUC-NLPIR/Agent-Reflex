"""Hand-reviewed EnvScaler RSD texts.

Source: RL rollouts from agentworld91_fixed_ck4386_rl and
agentworld92_2w_ck1875_rl, steps 1/10/21/30/41. I read the dumped
pos/neg traces in /tmp/rsd_review and the real tool lists from
train_envscaler_2550.jsonl. Only environments with readable contrast
are included. Texts are not tool-pipeline templates.
"""

from __future__ import annotations

# class_name -> analysis. env_id is filled at export time.
MANUAL_ANALYSIS: dict[str, dict] = {
    "ElectronicHealthRecordSystem": {
        "review_note": (
            "Best traces update_patient_info once but invent account_status=pending. "
            "Fail traces rewrite PAT1 as P-8000 and set suspended, then loop the same write."
        ),
        "bad_patterns": [
            "把题目里的当前登录患者（Alice Chan / PAT1）改写成自造编号（如 P-8000），还没调用 get_current_authenticated_patient 就连续 update_patient_info。",
            "把 account_status 写成环境里不存在的 pending / suspended，而题目要求的是 inactive。",
            "只改联系方式就结束，丢掉 2022-01-01 至 2024-12-31 的病历过滤，也不做 verify_medical_record_association。",
        ],
        "skills": [
            "先 get_current_authenticated_patient，确认回执里的 patient_id 就是题目中的 PAT1，再 update_patient_info；contact_info 与 account_status 一次写成题目给出的值，状态只用 inactive / active。",
            "病历用 filter_medical_records_by_date_range 取 2022–2024 的诊断和治疗，对每条 get_medical_record_details，再用 verify_medical_record_association 核提供者是 PROV1 / Dr. Samuel Hart。",
            "恢复账户前 list_patient_medical_records 看关联是否还在；不要用 add_medical_record 补一条脑补的心内科记录来代替校验。",
        ],
        "signatures": ["P-8000", "account_status\": \"pending", "account_status\": \"suspended"],
    },
    "VideoConferencingSchedulingSystem": {
        "review_note": (
            "Fail opens with edit_session_time and never reads participants. "
            "Higher-score traces still invent reschedule_session, which is not in the tool list."
        ),
        "bad_patterns": [
            "一上来就 edit_session_time，不先 get_session_by_id / get_session_participants，不知道谁 pending、谁已经是 creator。",
            "发明 reschedule_session；真实改期接口只有 edit_session_time。",
            "加人时不 get_user_by_email / get_user_by_id，直接把 creator 席位覆盖掉，或删除了仍是 active 的参会人。",
        ],
        "skills": [
            "先 get_session_by_id 和 get_session_participants，看清 account_status 与 role，再决定删谁、改谁。",
            "改期只走 edit_session_time；删人只删 pending / 非 active 的那位（如 U1003），creator 必须仍在 get_session_participants 里。",
            "加人先 get_user_by_email 或 get_user_by_id 拿到真实 user_id，再 add_participant_to_session，角色用 update_participant_role 改，不要重建整场会。",
        ],
        "signatures": ["reschedule_session", "edit_session_time"],
    },
    "HotelRoomReservationSystem": {
        "review_note": (
            "Zero-score traces call list_all_functions or a bare bookings tool and then dump R102/R104. "
            "Even the 'best' score 0.33 never listed the guest's real bookings."
        ),
        "bad_patterns": [
            "调用根本不存在的 list_all_functions 或 bookings，把房间号 R102 / R104 直接当成 booking_id。",
            "不 list_bookings_by_guest，因此取消不了 Alice / Jonathan 的原单，拆段预订变成在旧单上硬写。",
            "输出崩成重复房间号和语言碎片，没有任何 create_booking 回执。",
        ],
        "skills": [
            "先 list_bookings_by_guest(GUEST1 / GUEST2) 拿到真实 booking_id，要拆段就 cancel_booking 原单。",
            "新日期用 check_room_availability_over_date_range 确认不撞房，再 create_booking；工具名只使用列表里的那一套。",
            "每一步只接受回执里的 booking_id；房间号不是订单号，不要把 R102 写进 cancel_booking。",
        ],
        "signatures": ["list_all_functions", '"bookings"', "list_all_booking"],
    },
    "HospitalBedReservationSystem": {
        "review_note": (
            "Fail invents transfer_bed_assignments (plural) and mixes staff IDs with beds. "
            "Better traces often stay in think text and never list_available_beds_by_hospital."
        ),
        "bad_patterns": [
            "捏造 transfer_bed_assignments（复数）；环境里只有 transfer_bed_assignment。",
            "把 STF 工号、患者姓名和床位 ID 缠在同一参数里，不 get_patient_by_id / get_staff_by_id。",
            "跨院占床前不 list_available_beds_by_hospital，取消时误伤同一患者在本院的另一张有效预约。",
        ],
        "skills": [
            "题目给了 PAT-201 就 get_patient_by_id，不要按姓名另造患者；取消只用 list_reservations_by_patient 里指定医院/病区的那条，attribution 写题目里的 staff。",
            "新床先 list_available_beds_by_hospital，再 reserve_bed 或 create_reservation，最后 get_bed_info_by_id 看空闲标记是否变了。",
            "只有确认两边都是同一患者的不同床时才用 transfer_bed_assignment；不要把员工对象当成床。",
        ],
        "signatures": ["transfer_bed_assignments"],
    },
    "TelehealthAppointmentSchedulingSystem": {
        "review_note": (
            "Fail calls list_patient_appointments, then claims get_patient_appointments does not exist. "
            "The real list has get_patient_appointments. Higher traces plan a reschedule but leave cancelled slots booked."
        ),
        "bad_patterns": [
            "发明 list_patient_appointments；对不上表之后又误判 get_patient_appointments 不存在，整段改期停住。",
            "只在思考里“改时间”，不 release_timeslot，已取消预约仍占着 booked 槽。",
            "不 list_provider_available_time_slots / check_appointment_conflict 就 schedule_appointment，把患者或医生推进冲突槽。",
        ],
        "skills": [
            "现有预约用 get_patient_appointments 和 get_appointment_info，不要因为名字差一个词就放弃。",
            "改期先 list_provider_available_time_slots，用 check_appointment_conflict 选最早合法空槽，再 cancel_appointment 旧约、schedule_appointment 或 reschedule_appointment。",
            "扫仍标 booked 但预约已取消的槽，对它们 release_timeslot；不要只改 appointment 对象上的时间字段。",
        ],
        "signatures": ["list_patient_appointments", "does not exist"],
    },
    "BillingDisputeManagementSystem": {
        "review_note": (
            "Fail prefixes or truncates the UUID (DISP-643e9fcb...) and only loops validate_dispute_billing_item_relation. "
            "Best traces stay in think text and never resolve_dispute or write history."
        ),
        "bad_patterns": [
            "把 dispute_id 改写成 DISP- 前缀或截断 UUID，validate_dispute_billing_item_relation 对着错误主键空转。",
            "只做校验、不 assign_dispute_resolver，也不沿 get_allowed_resolution_status_values 改状态。",
            "口头说已结案，却没有 add_dispute_resolution_details / resolve_dispute，get_dispute_resolution_history 仍是空的。",
        ],
        "skills": [
            "dispute_id 原样使用题目里的 UUID，先 get_dispute_by_id 看当前 resolution_status。",
            "操作员用 get_operator_by_name 对齐 Alice / Samuel，再 assign_dispute_resolver；状态只能沿 get_allowed_resolution_status_values 逐步走（pending → in_review → accepted）。",
            "每步把 note 写入 add_dispute_resolution_details，需要结案时 resolve_dispute，最后用 get_dispute_resolution_history 证明不是口头结案。",
        ],
        "signatures": ["DISP-643e9fcb", "DISP-"],
    },
    "EcommerceProductReviewSystem": {
        "review_note": (
            "Fail treats PROD-003-USR-... as a review_id and calls update_review_moderation_status. "
            "Better traces add_product/add_user/add_review but skip rejecting pending reviews from inactive authors."
        ),
        "bad_patterns": [
            "用「PROD-003-USR-…」这种拼接串当 review_id 直接 update_review_moderation_status。",
            "新商品/新用户/新评价还没 add_product / add_user / add_review 就去审核一条并不存在的评价。",
            "不看作者 account_status，pending 评价该拒不拒，或再 add_review 一条重复评价来代替改状态。",
        ],
        "skills": [
            "新对象先 add_product / add_user / add_review，只使用回执里的 id。",
            "已有评价必须 get_reviews_for_product_by_status 或 get_review_by_id；作者 inactive 再把该条 update_review_moderation_status 为 rejected。",
            "改完再 get_reviews_for_product_by_status 确认 pending 清空，不要靠再写一条同样的评价交差。",
        ],
        "signatures": ["PROD-003-USR"],
    },
    "PersonalHealthRecordManagementSystem": {
        "review_note": (
            "Fail invents list_users_medication_relationships. "
            "Higher traces add_new_medication / add_medication_to_user instead of flipping Amlodipine inactive and Lisinopril active."
        ),
        "bad_patterns": [
            "发明 list_users_medication_relationships；真实列表是 list_user_medications / list_active_user_medications。",
            "把已在方案里的 Amlodipine / Lisinopril 再 add_new_medication 复制一条，而不是 update_user_medication_status。",
            "换药后不对当前活性集合做 get_drug_interactions_all_pairs，或继续给已停用的 Amlodipine 查交互。",
        ],
        "skills": [
            "先 list_active_user_medications。药已经在 USR5 方案里就 update_user_medication_status：Lisinopril (MEDC3) active，Amlodipine (MEDF6) inactive。",
            "只有题目要引入全新药名时才 add_new_medication；已有药不要复制。",
            "换降压药后立刻 get_drug_interactions_all_pairs，高严重冲突先停手；交互记录只挂在当前活性集合上。",
        ],
        "signatures": ["list_users_medication_relationships"],
    },
    "InsurancePolicyManagementSystem": {
        "review_note": (
            "Both best and fail hallucinate get_policy_after_initial_information and invent CEN- policy numbers. "
            "transfer_policy_to_new_insured_party exists but the task was coverage edit, not transfer."
        ),
        "bad_patterns": [
            "幻觉 get_policy_after_initial_information，并把 XJ-439220 改成 CEN- 开头的随机保单号。",
            "任务是加 Psychiatric Care 保障，却去调用 transfer_policy_to_new_insured_party，保障项从未写入。",
            "不加 get_exclusions_for_policy，精神科 exclusion 还在就 add_coverage_item_to_policy，回读限额也没有。",
        ],
        "skills": [
            "用题目给的 policy number 走 get_policy_by_policy_number，并 is_authorized_user_for_policy；不要改写保单号。",
            "加精神科责任前先 get_exclusions_for_policy，挡住 Psychiatric Care 的 exclusion 先 remove_exclusion_from_policy，再 add_coverage_item_to_policy。",
            "限额/免赔额用 update_coverage_limit_or_deductible 写完后，get_coverage_limits_and_deductibles 回读；转保接口留给真正要换投保人的任务。",
        ],
        "signatures": ["get_policy_after_initial_information", "CEN-90167234", "CEN-"],
    },
    "ClassSchedulingRegistrationSystem": {
        "review_note": (
            "Fail emits a lone hallucinated register tool. "
            "Best traces collapse into garbled session_id tokens and never create the 11:30 Yoga Basics."
        ),
        "bad_patterns": [
            "调用不存在的 register；真实报名接口是 register_user_for_session。",
            "不 find_class_sessions / create_class_session，11:30 的新 Yoga Basics 从未被创建。",
            "不 check_user_schedule_conflict / check_class_capacity，Alice 也没有从 09:00 那节 cancel_user_registration。",
        ],
        "skills": [
            "先 find_class_sessions 确认当天已有的 09:00 Yoga Basics、导师和教室。",
            "新课用 create_class_session 写 11:30–12:30、capacity 10、Sean Avery、Central City Studio，并用 check_user_schedule_conflict、check_class_capacity。",
            "Alice 先 cancel_user_registration 旧 session，再 register_user_for_session 到新课；John 只注册新课，别人的报名不要动。",
        ],
        "signatures": ['"register"', "register_user_for_session"],
    },
    "HospitalMealManagementSystem": {
        "review_note": (
            "Best calls get_patient_meal_assignments, which the environment rejects. "
            "Fail writes update_meal_properties with invented meal_id M101 and broken JSON."
        ),
        "bad_patterns": [
            "调用未暴露的 get_patient_meal_assignments，被环境直接打回。",
            "不读 get_patient_dietary_restrictions，按病名猜套餐，把含过敏原的餐派下去。",
            "update_meal_properties 使用自造 meal_id（如 M101），或不先 list_all_meals 对齐真实菜名。",
        ],
        "skills": [
            "get_patient_by_id 之后先 get_patient_dietary_restrictions，再用 get_meals_available_for_patient_at_datetime 过滤。",
            "只从过滤结果里 assign_meal_to_patient；派餐后再 get_meal_schedule_by_datetime 核对。",
            "改禁忌先 update_patient_dietary_restrictions 再派餐；改菜谱先 list_all_meals / get_meal_by_id 拿到真 meal_id，再 update_meal_properties 或 update_meal_allergen_info。",
        ],
        "signatures": ["get_patient_meal_assignments", "M101"],
    },
    "DiseaseOutbreakAlertSubscriptionSystem": {
        "review_note": (
            "Higher traces only poll get_outbreaks_near_location and treat that as a subscription change. "
            "Fail jumps to update_subscription_location without validating the subscriber or the new point."
        ),
        "bad_patterns": [
            "只打 get_outbreaks_near_location，把「附近有疫情」当成已经改完订阅。",
            "不 get_subscriber_by_email 就 update_subscription_location，也不 validate_location。",
            "create_subscription 之后不 activate_subscription，或在已有坐标上再订一次造成重复。",
        ],
        "skills": [
            "邮箱先 get_subscriber_by_email，没有再 create_subscriber；地点必须 validate_location。",
            "迁点前 list_subscriptions_for_subscriber，对要停的点 deactivate_subscription，对要改的点 update_subscription_location。",
            "新点先 check_subscription_exists_for_location，没有再 create_subscription 并 activate_subscription，最后 get_active_subscriptions 能看到该坐标。",
        ],
        "signatures": ["update_subscription_location"],
    },
    "PublicHealthOutbreakReportingSystem": {
        "review_note": (
            "Best calls list_outbreak_reports, which is not a tool (real names are list_reports_by_*). "
            "Fail creates a report with a free-text location string and never verifies it."
        ),
        "bad_patterns": [
            "幻觉 list_outbreak_reports；真实列举是 list_reports_by_location / list_reports_by_disease。",
            "create_outbreak_report 把地点写成一段地址字符串，不 get_location_by_name，病种也不在 list_notifiable_diseases 里核对。",
            "把 create 当成已经发布：不 validate_reporter_credentials，也不 verify_outbreak_report，却对用户说爆发已确认。",
        ],
        "skills": [
            "病种必须落在 list_notifiable_diseases，地点用 get_location_by_name，报告人用 get_reporter_by_id。",
            "create_outbreak_report 只产生待核记录；有核验权限再 verify_outbreak_report，必要时 escalate_outbreak_report。",
            "get_report_status 仍是 submitted / draft / pending 时，不要说爆发已确认；link_report_to_location 补上地点关联。",
        ],
        "signatures": ["list_outbreak_reports"],
    },
    "EcommerceOrderManagementSystem": {
        "review_note": (
            "Fail invents list_user_carts / merge_carts and never resolves the user. "
            "Best traces stop after realizing there is no get-user-by-name in their imagined API — but get_user_by_name exists."
        ),
        "bad_patterns": [
            "幻觉 list_user_carts、merge_carts；购物车接口是 get_cart_by_user_id / create_cart_for_user。",
            "误以为不能按姓名找人，空转；真实有 get_user_by_name。",
            "用商品中文名当 product_id 加车，或不 get_product_stock_quantity 就 add_product_to_cart。",
        ],
        "skills": [
            "get_user_by_name 拿到 user_id，再 get_cart_by_user_id；没有车就 create_cart_for_user。",
            "商品用 get_product_by_name 落到 id，get_product_stock_quantity 够才 add_product_to_cart 或 update_cart_item_quantity。",
            "改完 list_cart_items，对净增量 decrement_product_stock_quantity，并用 set_cart_updated_time；展示名不要写进车。",
        ],
        "signatures": ["list_user_carts", "merge_carts"],
    },
    "HospitalBillingManagementSystem": {
        "review_note": (
            "Best wraps real-looking names inside a fake actions tool. "
            "Fail invents create_customer_support_interaction; the real logger is log_customer_support_interaction."
        ),
        "bad_patterns": [
            "发明 actions / update_bill_payment_adjustment 外壳，真实改账是 modify_bill_details、add_payment_to_bill、update_bill_status。",
            "幻觉 create_customer_support_interaction；记录沟通只用 log_customer_support_interaction。",
            "不 get_bill_by_id / get_dispute_by_id 就改金额，患者联系方式与账单主键对不齐。",
        ],
        "skills": [
            "先 get_patient_by_id、get_bill_by_id、get_dispute_by_id，看清 BILL3 / D3 的当前金额和争议状态。",
            "撤项用 modify_bill_details，收款用 add_payment_to_bill，账单状态用 update_bill_status；争议用 update_dispute_status 和 add_dispute_resolution_detail。",
            "客服记录走 log_customer_support_interaction；需要改电话邮件再用 update_patient_contact_information，不要包进自造的 actions。",
        ],
        "signatures": ['"actions"', "update_bill_payment_adjustment", "create_customer_support_interaction"],
    },
    "YogaClassBookingSystem": {
        "review_note": (
            "Init leak made empty rollouts score 0.4–0.7 because 'user/class is active' "
            "was already true. After stripping those checks, remaining work is cancel/"
            "enroll/find-next-slot, which empty traces never do."
        ),
        "bad_patterns": [
            "把「用户 active / 课程 active」当成任务完成，空输出也能吃到泄漏分。",
            "不 find 下一节有空位的课，也不 cancel 残障/冲突报名，只在已有 CLS 上空转。",
            "发明不存在的 register 入口；真实是环境里的报名/取消接口。",
        ],
        "skills": [
            "先用列表里的课程查询确认目标课，但不要把 status=active 当成交差。",
            "要改名单就 cancel 冲突或 disabled 用户的报名，再为题目指定的用户写 enrollment；回执里要能看到该 user_id。",
            "找下一节晚课或指定 instructor specialty 时，按日期窗口和 remaining capacity 选课，不要沿用已经满员或时间不对的 CLS。",
        ],
        "signatures": [],
    },
    "TelemedicineDermatologyPlatform": {
        "review_note": (
            "Both sides invent authenticate_and_roles / authenticate_user. "
            "create_consultation is real, but they pass email strings as patient_id / provider_id."
        ),
        "bad_patterns": [
            "幻觉 authenticate_and_roles / authenticate_user；认证是 check_user_authentication，身份是 get_user_by_email / get_user_role。",
            "create_consultation 把邮箱字符串直接当作 patient_id / provider_id，咨询主键也自己编。",
            "不 upload_image_to_consultation，或上传后不 update_image_metadata / restrict_image_access，旧图也不 remove_image_from_consultation。",
        ],
        "skills": [
            "用 get_user_by_email 对齐 Alice / 医生，再 check_user_authentication 和 get_user_role，不要发明登录工具。",
            "create_consultation 使用回执或题目里的内部 id；图用 upload_image_to_consultation，元数据走 update_image_metadata，可见性走 restrict_image_access。",
            "需要替换旧图时 list_images_for_consultation，确认 can_user_access_image 后再 remove_image_from_consultation，并用 update_consultation_note 写下记录。",
        ],
        "signatures": ["authenticate_and_roles", "authenticate_user"],
    },
}

SKIPPED_REASON = {
    "FitnessEquipmentManagementSystem": "steps 1/10 dumps were unreadable token salad; no executable pos/neg contrast",
    "HospitalPatientManagementSystem": "large task volume but I did not finish a clean paired read in this pass",
    "FitnessChallengePlatform": "almost no positive traces in the sampled steps",
    "OnlinePharmacyOrderManagementSystem": "not personally re-read in this pass",
    "ContactLensSubscriptionManagementSystem": "high mean reward, but I did not audit a paired failure this pass",
}
