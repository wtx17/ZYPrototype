"""WebSocket connection manager for real-time customer support messaging.

Tracks connected clients (customers, CS agents, RD agents) and routes messages
between them. Handles ticket assignment, escalation, and service lifecycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import WebSocket

from database import (
    insert_message,
    insert_ticket,
    assign_ticket_cs,
    assign_ticket_rd,
    update_ticket_customer,
    end_ticket_service,
    list_active_tickets_for_agent,
    get_ticket,
)
from models import TicketStatus

logger = logging.getLogger("ws_manager")


class WSClients:
    """In-memory registry of all connected WebSocket clients."""

    def __init__(self):
        self.customers: dict[str, WebSocket] = {}       # customer_id -> ws
        self.cs_agents: dict[str, WebSocket] = {}       # cs_username -> ws
        self.rd_agents: dict[str, WebSocket] = {}       # rd_username -> ws
        self.cs_users: dict[str, int] = {}              # cs_username -> user_id
        self.rd_users: dict[str, int] = {}              # rd_username -> user_id
        self.ticket_map: dict[int, str] = {}            # ticket_id -> customer_id
        self.ticket_cs: dict[int, str] = {}             # ticket_id -> cs_username
        self.ticket_rd: dict[int, str] = {}             # ticket_id -> rd_username

    # --- Registration ---

    DEFAULT_CS = "小陈"

    async def register_customer(self, customer_id: str, ws: WebSocket):
        self.customers[customer_id] = ws

    async def register_cs(self, username: str, ws: WebSocket, user_id: int = 0):
        self.cs_agents[username] = ws
        if user_id:
            self.cs_users[username] = user_id

    async def register_rd(self, username: str, ws: WebSocket, user_id: int = 0):
        self.rd_agents[username] = ws
        if user_id:
            self.rd_users[username] = user_id

    # --- Deregistration ---

    async def unregister_customer(self, customer_id: str):
        self.customers.pop(customer_id, None)

    async def unregister_cs(self, username: str):
        self.cs_agents.pop(username, None)
        self.cs_users.pop(username, None)

    async def unregister_rd(self, username: str):
        self.rd_agents.pop(username, None)
        self.rd_users.pop(username, None)

    # --- Routing ---

    async def send_to_customer(self, ticket_id: int, message: dict):
        customer_id = self.ticket_map.get(ticket_id)
        if customer_id and customer_id in self.customers:
            ws = self.customers[customer_id]
            await ws.send_json(message)

    async def send_to_cs(self, ticket_id: int, message: dict):
        cs_name = self.ticket_cs.get(ticket_id)
        if cs_name and cs_name in self.cs_agents:
            ws = self.cs_agents[cs_name]
            await ws.send_json(message)

    async def send_to_rd(self, ticket_id: int, message: dict):
        rd_name = self.ticket_rd.get(ticket_id)
        if rd_name and rd_name in self.rd_agents:
            ws = self.rd_agents[rd_name]
            await ws.send_json(message)

    async def send_to_all_rd(self, message: dict):
        for ws in self.rd_agents.values():
            await ws.send_json(message)

    async def send_to_all_cs(self, message: dict):
        for ws in self.cs_agents.values():
            await ws.send_json(message)

    # --- Business Logic ---

    async def handle_customer_message(self, ticket_id: int, content: str, customer_id: str) -> int:
        """Customer sends a message → persist + forward.
        If ticket_id is 0 or None, creates a new ticket on first message.
        Returns the ticket_id."""
        if not ticket_id:
            ticket_id = self._create_ticket_for_customer(customer_id, content)
            # Notify all CS agents about new ticket
            ticket = get_ticket(ticket_id)
            await self.send_to_all_cs({
                "type": "new_session",
                "payload": {
                    "ticket_id": ticket_id,
                    "title": ticket.get("title", "") if ticket else "",
                    "customer_id": customer_id,
                },
            })

        insert_message(ticket_id, "customer", customer_id, content)
        ticket = get_ticket(ticket_id)

        msg = {
            "type": "customer_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": content,
                "sender_name": customer_id,
                "ticket_title": ticket.get("title", "") if ticket else "",
            },
        }
        await self.send_to_cs(ticket_id, msg)
        return ticket_id

    async def handle_cs_accept(self, ticket_id: int, cs_name: str):
        """CS accepts a ticket. Assigns CS and sends greeting to customer."""
        user_id = self.cs_users.get(cs_name, 0)
        assign_ticket_cs(ticket_id, user_id)
        self.ticket_cs[ticket_id] = cs_name
        greeting = f"客服 {cs_name} 为您服务"
        insert_message(ticket_id, "system", "系统", greeting)
        await self.send_to_customer(ticket_id, {
            "type": "system_message",
            "payload": {"ticket_id": ticket_id, "content": greeting},
        })

    def _create_ticket_for_customer(self, customer_id: str, content: str) -> int:
        """Create a ticket on first customer message. No auto-assignment."""
        from database import get_or_create_user
        user = get_or_create_user(customer_id, customer_id, "customer")
        title = content[:80] if len(content) > 80 else content
        ticket_id = insert_ticket({
            "title": title,
            "description": content,
            "status": TicketStatus.PENDING.value,
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        update_ticket_customer(ticket_id, user["id"])
        self.ticket_map[ticket_id] = customer_id
        return ticket_id

    async def handle_agent_message(self, ticket_id: int, content: str, sender_type: str, sender_name: str):
        """CS or RD sends a message → persist + forward to customer."""
        insert_message(ticket_id, sender_type, sender_name, content)
        msg = {
            "type": "agent_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": content,
                "sender_name": sender_name,
                "sender_type": sender_type,
            },
        }
        await self.send_to_customer(ticket_id, msg)

    async def handle_escalate(self, ticket_id: int, reason: str = ""):
        """CS escalates ticket to RD. Notify RD agents, remove CS from ticket."""
        from database import escalate_ticket as db_escalate
        db_escalate(ticket_id, reason or "客服主动升级")
        insert_message(ticket_id, "system", "系统", "正在为您升级工单，工程师即将接入")
        update_ticket_status_db(ticket_id, TicketStatus.ESCALATED.value)

        # Notify customer
        await self.send_to_customer(ticket_id, {
            "type": "system_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": "正在为您升级工单，工程师即将接入",
            },
        })

        # Notify CS to exit and clear assignment
        cs_name = self.ticket_cs.get(ticket_id)
        if cs_name and cs_name in self.cs_agents:
            await self.cs_agents[cs_name].send_json({
                "type": "escalation_transfer",
                "payload": {"ticket_id": ticket_id, "action": "exit"},
            })
        self.ticket_cs.pop(ticket_id, None)
        # Clear assigned_cs so ticket leaves CS session list
        from database import clear_ticket_cs
        clear_ticket_cs(ticket_id)

        # Notify all RD agents
        ticket = get_ticket(ticket_id)
        await self.send_to_all_rd({
            "type": "new_escalation",
            "payload": {
                "ticket_id": ticket_id,
                "title": ticket.get("title", "") if ticket else "",
                "reason": reason,
            },
        })

    async def handle_rd_accept(self, ticket_id: int, rd_name: str):
        """RD accepts an escalated ticket. Takes over the conversation."""
        user_id = self.rd_users.get(rd_name, 0)
        assign_ticket_rd(ticket_id, user_id)
        self.ticket_rd[ticket_id] = rd_name
        insert_message(ticket_id, "system", "系统", f"工程师 {rd_name} 为您服务")

        await self.send_to_customer(ticket_id, {
            "type": "system_message",
            "payload": {
                "ticket_id": ticket_id,
                "content": f"工程师 {rd_name} 为您服务",
            },
        })

    async def handle_service_end(self, ticket_id: int):
        """Agent ends service. Notify customer to fill satisfaction survey."""
        end_ticket_service(ticket_id)
        insert_message(ticket_id, "system", "系统", "服务已结束")

        await self.send_to_customer(ticket_id, {
            "type": "service_end",
            "payload": {
                "ticket_id": ticket_id,
                "content": "您的问题是否已解决？",
            },
        })

        # Notify both CS and RD to clean up
        cs_name = self.ticket_cs.pop(ticket_id, None)
        if cs_name and cs_name in self.cs_agents:
            await self.cs_agents[cs_name].send_json({
                "type": "ticket_closed",
                "payload": {"ticket_id": ticket_id},
            })
        rd_name = self.ticket_rd.pop(ticket_id, None)
        if rd_name and rd_name in self.rd_agents:
            await self.rd_agents[rd_name].send_json({
                "type": "ticket_closed",
                "payload": {"ticket_id": ticket_id},
            })

    async def handle_satisfaction(self, ticket_id: int, resolved: str, feedback_text: str = ""):
        """Customer submits satisfaction feedback."""
        from database import insert_satisfaction_feedback
        insert_satisfaction_feedback(ticket_id, resolved, feedback_text)

    def get_available_cs_count(self) -> int:
        return len(self.cs_agents)

    def get_available_rd_count(self) -> int:
        return len(self.rd_agents)


def update_ticket_status_db(ticket_id: int, status: str):
    """Update ticket status in database."""
    from database import update_ticket_status
    update_ticket_status(ticket_id, status)


# Singleton
clients = WSClients()
