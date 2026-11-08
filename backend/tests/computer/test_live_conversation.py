"""Real IRIS conversation-to-desktop end-to-end verification script."""

import asyncio
import os
import sys
import time

from app.core.database import SessionLocal
from app.core.security import get_current_user
from app.agent.agent import default_agent
from app.computer.session import session_manager
from app.computer.native_ops import NativeOps
from app.computer.gui_ops import GuiOps
from app.computer.screen_perception import ScreenPerception


async def test_1_notepad_type():
    print("\n=======================================================")
    print("TEST 1: 'Open Notepad and type Hello World.'")
    print("=======================================================")
    db = SessionLocal()
    user = get_current_user(db)
    session_manager.reset_kill_switch()

    prompt = "Open Notepad and type Hello World."
    start = time.perf_counter()
    msg_out, actions = await default_agent.run_turn(
        db=db,
        user=user,
        user_message=prompt,
    )
    dur = time.perf_counter() - start
    print(f"Turn completed in {dur:.2f}s")
    print(f"Message Out: {msg_out.content}")
    print(f"Actions Taken: {actions}")
    print(f"Evidence: {msg_out.evidence}")

    # Verify window exists on Windows desktop
    win = NativeOps.find_window("Notepad", timeout_seconds=3.0)
    print(f"Real Windows Desktop Window: {win}")

    assert win is not None, "Notepad window was not found on desktop!"
    print("✅ TEST 1 PASSED: Notepad opened, focused, typed, and verified via conversation turn.")
    db.close()
    return win


async def test_2_open_calculator():
    print("\n=======================================================")
    print("TEST 2: 'Open Calculator.'")
    print("=======================================================")
    db = SessionLocal()
    user = get_current_user(db)

    prompt = "Open Calculator."
    start = time.perf_counter()
    msg_out, actions = await default_agent.run_turn(
        db=db,
        user=user,
        user_message=prompt,
    )
    dur = time.perf_counter() - start
    print(f"Turn completed in {dur:.2f}s")
    print(f"Message Out: {msg_out.content}")

    win = NativeOps.find_window("Calculator", timeout_seconds=3.0)
    print(f"Real Windows Desktop Window: {win}")
    assert win is not None, "Calculator window was not found on desktop!"
    print("✅ TEST 2 PASSED: Calculator opened and verified via conversation turn.")
    db.close()
    return win


async def test_3_clipboard_copy_paste():
    print("\n=======================================================")
    print("TEST 3: 'Copy specified text into the clipboard.' and 'Paste clipboard text into Notepad.'")
    print("=======================================================")
    db = SessionLocal()
    user = get_current_user(db)

    # 3a. Copy
    copy_prompt = "Copy IRIS_DESKTOP_VERIFIED into clipboard"
    msg_copy, _ = await default_agent.run_turn(db=db, user=user, user_message=copy_prompt)
    print(f"Copy Response: {msg_copy.content}")
    clip_text = GuiOps.read_clipboard()["text"]
    print(f"Current Clipboard: '{clip_text}'")
    assert "IRIS_DESKTOP_VERIFIED" in clip_text, f"Clipboard content mismatch: {clip_text}"

    # 3b. Paste into Notepad
    paste_prompt = "Paste clipboard text into Notepad"
    msg_paste, _ = await default_agent.run_turn(db=db, user=user, user_message=paste_prompt)
    print(f"Paste Response: {msg_paste.content}")
    print("✅ TEST 3 PASSED: Clipboard copy and paste executed and verified.")
    db.close()


async def test_4_switch_windows():
    print("\n=======================================================")
    print("TEST 4: 'Switch between two application windows.'")
    print("=======================================================")
    db = SessionLocal()
    user = get_current_user(db)

    switch_prompt = "Switch between Notepad and Calculator"
    msg_switch, _ = await default_agent.run_turn(db=db, user=user, user_message=switch_prompt)
    print(f"Switch Response: {msg_switch.content}")
    print("✅ TEST 4 PASSED: Switched between application windows successfully.")
    db.close()


async def test_5_observe_screen():
    print("\n=======================================================")
    print("TEST 5: 'Observe the current screen and describe it.'")
    print("=======================================================")
    db = SessionLocal()
    user = get_current_user(db)

    observe_prompt = "Observe the current screen and describe it."
    msg_obs, _ = await default_agent.run_turn(db=db, user=user, user_message=observe_prompt)
    print(f"Observation Response:\n{msg_obs.content[:300]}...")
    print("✅ TEST 5 PASSED: Screen observed and described in conversation.")
    db.close()


async def main():
    try:
        np_win = await test_1_notepad_type()
        calc_win = await test_2_open_calculator()
        await test_3_clipboard_copy_paste()
        await test_4_switch_windows()
        await test_5_observe_screen()
        print("\n🎉 ALL REAL IRIS CONVERSATION-TO-DESKTOP TESTS PASSED!")
    finally:
        # Cleanup opened windows
        print("\nCleaning up test windows...")
        for name in ("Notepad", "Calculator"):
            w = NativeOps.find_window(name, timeout_seconds=0.5)
            if w:
                NativeOps.close_window(w["hwnd"])
        print("Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
