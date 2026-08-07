-- تحصين سياسات الكتابة لجدول official_transactions (منشورة بعد 005 بسياسات مفتوحة)
-- تُستخدم للأمان: أي دور anon لا يملك حق الإدراج/التعديل/الحذف، والكتابة لدور service_role فقط.

drop policy if exists "service write official_transactions" on official_transactions;
drop policy if exists "service update official_transactions" on official_transactions;
drop policy if exists "service delete official_transactions" on official_transactions;

create policy "service write official_transactions"
  on official_transactions for insert to service_role
  with check (true);

create policy "service update official_transactions"
  on official_transactions for update to service_role
  using (true);

create policy "service delete official_transactions"
  on official_transactions for delete to service_role
  using (true);
