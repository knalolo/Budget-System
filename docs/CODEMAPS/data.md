<!-- Generated: 2026-03-31 | Models: 10 | Migrations: 10 | Token estimate: ~800 -->
# Data

## Models (10 total, 7 apps)

### accounts
```
UserProfile [1:1 User, related_name="profile"]
  role (CharField) → ROLE_CHOICES: requester|pcm_approver|final_approver|admin
  display_name, azure_oid (unique, nullable)
  Properties: is_pcm_approver, is_final_approver, is_admin
  Auto-created via post_save signal on User
```

### core
```
FileAttachment [GenericFK → any model]
  content_type + object_id + content_object
  file (upload_to="attachments/%Y/%m/"), original_filename, file_type, file_size
  uploaded_by → User (SET_NULL)
  Index: (content_type, object_id)

SystemConfig
  key (unique), value (JSON-encoded TextField), description
  Class methods: get_value(key, default), set_value(key, value)

EmailNotificationLog [GenericFK → any model, optional]
  content_type + object_id (both nullable)
  recipients (JSONField), cc_recipients (JSONField), subject, body
  status: pending|sent|failed
  Index: status, (content_type, object_id)
```

### orders
```
Project
  mc_number (unique), name, is_active

ExpenseCategory
  name (unique), is_active

PurchaseRequest
  request_number (unique, auto: "PR-YYYYMMDD-XXXX")
  requester → User, project → Project (PROTECT), expense_category → ExpenseCategory (PROTECT)
  description, vendor, currency, total_price (14,2), justification, po_required, target_payment
  status → PR_STATUS_CHOICES (8 states)
  pcm_approver → User, pcm_decision, pcm_comment, pcm_decided_at
  final_approver → User, final_decision, final_comment, final_decided_at
  GenericRelation: attachments, approval_logs
  Properties: is_draft, is_pending, is_approved, is_rejected, can_be_edited, can_be_deleted, requires_po
```

### payments
```
PaymentRelease
  request_number (unique, auto: "RP-YYYYMMDD-XXXX", syncs from linked PR)
  purchase_request → PurchaseRequest (SET_NULL, optional)
  requester → User, project → Project (PROTECT), expense_category → ExpenseCategory (PROTECT)
  description, vendor, currency, total_price, justification, po_number, target_payment
  status → PAYMENT_STATUS_CHOICES (5 states)
  pcm_approver/final_approver → User + decision/comment/decided_at fields
  GenericRelation: attachments, approval_logs
```

### deliveries
```
DeliverySubmission
  request_number (unique, auto: "DO-YYYYMMDD-XXXX")
  purchase_request → PurchaseRequest (SET_NULL, optional)
  requester → User, vendor, currency, total_price
  status: submitted|saved
  GenericRelation: attachments
```

### approvals
```
ApprovalLog [GenericFK → any model]
  content_type + object_id
  action: submitted|pcm_approved|pcm_rejected|final_approved|final_rejected|status_changed
  action_by → User, comment, old_status, new_status
  Index: (content_type, object_id)
```

### assets
```
AssetRegistration
  payment_release → PaymentRelease (SET_NULL, optional)
  purchase_request → PurchaseRequest (SET_NULL, optional)
  requester → User, status: draft|pending_export|exported|imported, notes

AssetItem
  registration → AssetRegistration (CASCADE, related_name="items")
  asset_name, asset_tag, category, serial_number
  purchase_date, purchase_cost (14,2), supplier, location, department, assigned_to, notes
```

## Relationship Map

```
User ──1:1──→ UserProfile
User ──1:N──→ PurchaseRequest (as requester, pcm_approver, final_approver)
User ──1:N──→ PaymentRelease (same pattern)
User ──1:N──→ DeliverySubmission, AssetRegistration, ApprovalLog, FileAttachment

Project ←──N:1── PurchaseRequest, PaymentRelease
ExpenseCategory ←──N:1── PurchaseRequest, PaymentRelease

PurchaseRequest ──1:N──→ PaymentRelease, DeliverySubmission, AssetRegistration
PaymentRelease ──1:N──→ AssetRegistration

ContentType + object_id (GenericFK):
  FileAttachment → PurchaseRequest, PaymentRelease, DeliverySubmission
  ApprovalLog → PurchaseRequest, PaymentRelease
  EmailNotificationLog → PurchaseRequest, PaymentRelease
```

## Migration Count by App

accounts: 1 | core: 1 | orders: 2 | payments: 2 | deliveries: 1 | approvals: 1 | assets: 2
