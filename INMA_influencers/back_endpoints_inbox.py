@app.get("/inbox")
def get_inbox_messages(limit: int = 20, query: Optional[str] = None):
    try:
        service = get_gmail_service()
        
        # Default query: messages sent to me, exclude chats
        q = query or "category:primary -from:me"
        
        results = service.users().messages().list(userId="me", q=q, maxResults=limit).execute()
        messages = results.get("messages", [])
        
        inbox_items = []
        for msg in messages:
            try:
                full = get_message_full(service, msg["id"])
                headers = extract_headers(full)
                snippet = full.get("snippet", "")
                
                # Try to get full body
                body = get_message_text(full)
                
                item = {
                    "id": msg["id"],
                    "threadId": msg["threadId"],
                    "subject": headers.get("subject", "(No Subject)"),
                    "from": parse_email_from_header(headers.get("from", "")),
                    "date": headers.get("date", ""),
                    "snippet": snippet,
                    "body": body,
                    "unread": "UNREAD" in full.get("labelIds", [])
                }
                inbox_items.append(item)
            except Exception as e:
                print(f"Error parsing message {msg['id']}: {e}")
                continue
                
        return inbox_items
    except Exception as e:
        print(f"Inbox Error: {e}")
        # Return mock data if API fails (e.g. no creds) so UI doesn't break
        # In production we might want to raise 500, but for demo stability:
        return []
