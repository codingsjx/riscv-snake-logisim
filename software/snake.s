# RV32 snake for the supplied Logisim forwarding pipeline.
# Only course base instructions are used; no MUL/DIV/LUI/AUIPC/variable shifts.
# Private calling convention: ra/sp/s11 preserved, other registers are scratch.
# RAM: 0 length,4 tail,8 head,12 direction,16 food,20 RNG,24 status,
# 28 score,32 last tick,36 previous keys,40 pending direction,44 high score.
# Queue 0x100..0x4ff (256 words); mask table 0x500..0x53f; stack top 0x680.
# MMIO: 0x700 keys; 0x704 cycle counter; 0x708 move interval.
# Framebuffer 0x740..0x77c, metadata 0x780..0x798; see README.

start:
    addi sp, zero, 1664
    addi s11, zero, 1792
    sw zero, 44(zero)
    addi t0, zero, 1280
    addi t1, zero, 1
    slli t1, t1, 15
    addi t2, zero, 16
init_masks:
    sw t1, 0(t0)
    srli t1, t1, 1
    addi t0, t0, 4
    addi t2, t2, -1
    bne t2, zero, init_masks
    jal ra, game_reset

main:
    lw t0, 0(s11)
    lw t1, 36(zero)
    sw t0, 36(zero)
    xori t1, t1, -1
    and t1, t0, t1
    addi t6, t1, 0
    andi t2, t1, 64
    bne t2, zero, restart
    andi t2, t1, 16
    beq t2, zero, check_pause
    lw t2, 24(zero)
    beq t2, zero, begin_game
check_pause:
    andi t2, t1, 32
    beq t2, zero, check_direction
    lw t2, 24(zero)
    addi t3, zero, 1
    beq t2, t3, pause_game
    addi t3, zero, 2
    beq t2, t3, resume_game
check_direction:
    lw t2, 24(zero)
    addi t3, zero, 1
    bne t2, t3, main
    lw t2, 12(zero)
    # Direction codes: 0 up, 1 right, 2 down, 3 left.
    # Compare to committed direction, so fast multiple presses cannot reverse.
    andi t3, t0, 1
    beq t3, zero, try_right
    addi t4, zero, 2
    beq t2, t4, check_time
    sw zero, 40(zero)
    jal zero, check_time
try_right:
    andi t3, t0, 2
    beq t3, zero, try_down
    addi t4, zero, 3
    beq t2, t4, check_time
    addi t4, zero, 1
    sw t4, 40(zero)
    jal zero, check_time
try_down:
    andi t3, t0, 4
    beq t3, zero, try_left
    beq t2, zero, check_time
    addi t4, zero, 2
    sw t4, 40(zero)
    jal zero, check_time
try_left:
    andi t3, t0, 8
    beq t3, zero, check_time
    addi t4, zero, 1
    beq t2, t4, check_time
    addi t4, zero, 3
    sw t4, 40(zero)
check_time:
    lw t0, 4(s11)
    andi t3, t6, 128
    bne t3, zero, move_now
    lw t1, 32(zero)
    sub t1, t0, t1
    lw t2, 8(s11)
    sltu t3, t1, t2
    bne t3, zero, main
move_now:
    sw t0, 32(zero)
    lw t1, 40(zero)
    sw t1, 12(zero)
    jal ra, game_step
    jal ra, render
    jal zero, main
restart:
    jal ra, game_reset
    jal zero, main
begin_game:
    addi t2, zero, 1
    sw t2, 24(zero)
    lw t0, 4(s11)
    sw t0, 32(zero)
    jal ra, render
    jal zero, main
pause_game:
    addi t2, zero, 2
    sw t2, 24(zero)
    jal ra, render
    jal zero, main
resume_game:
    addi t2, zero, 1
    sw t2, 24(zero)
    lw t0, 4(s11)
    sw t0, 32(zero)
    jal ra, render
    jal zero, main

game_reset:
    addi sp, sp, -16
    sw ra, 12(sp)
    addi t0, zero, 3
    sw t0, 0(zero)
    sw zero, 4(zero)
    addi t0, zero, 2
    sw t0, 8(zero)
    addi t0, zero, 1
    sw t0, 12(zero)
    sw t0, 40(zero)
    addi t0, zero, 139
    sw t0, 16(zero)
    addi t0, zero, 37
    sw t0, 20(zero)
    sw zero, 24(zero)
    sw zero, 28(zero)
    lw t0, 4(s11)
    sw t0, 32(zero)
    lw t0, 0(s11)
    sw t0, 36(zero)
    addi t0, zero, 133
    sw t0, 256(zero)
    addi t0, zero, 134
    sw t0, 260(zero)
    addi t0, zero, 135
    sw t0, 264(zero)
    jal ra, render
    lw ra, 12(sp)
    addi sp, sp, 16
    jalr zero, 0(ra)

game_step:
    addi sp, sp, -16
    sw ra, 12(sp)
    lw t0, 8(zero)
    slli t0, t0, 2
    addi t0, t0, 256
    lw s0, 0(t0)
    andi t1, s0, 15
    srli t2, s0, 4
    lw t0, 12(zero)
    beq t0, zero, move_up
    addi t3, zero, 1
    beq t0, t3, move_right
    addi t3, zero, 2
    beq t0, t3, move_down
    beq t1, zero, lose
    addi s0, s0, -1
    jal zero, collision
move_up:
    beq t2, zero, lose
    addi s0, s0, -16
    jal zero, collision
move_right:
    addi t3, zero, 15
    beq t1, t3, lose
    addi s0, s0, 1
    jal zero, collision
move_down:
    addi t3, zero, 15
    beq t2, t3, lose
    addi s0, s0, 16
collision:
    lw t0, 16(zero)
    sub t0, s0, t0
    sltu s1, zero, t0
    xori s1, s1, 1
    lw t0, 4(zero)
    lw t1, 0(zero)
    # A departing tail cell is legal when the snake does not grow.
    bne s1, zero, collision_loop
    addi t0, t0, 1
    andi t0, t0, 255
    addi t1, t1, -1
collision_loop:
    beq t1, zero, accept_move
    slli t2, t0, 2
    addi t2, t2, 256
    lw t3, 0(t2)
    beq t3, s0, lose
    addi t0, t0, 1
    andi t0, t0, 255
    addi t1, t1, -1
    jal zero, collision_loop
accept_move:
    lw t0, 8(zero)
    addi t0, t0, 1
    andi t0, t0, 255
    sw t0, 8(zero)
    slli t0, t0, 2
    addi t0, t0, 256
    sw s0, 0(t0)
    bne s1, zero, grow
    lw t0, 4(zero)
    addi t0, t0, 1
    andi t0, t0, 255
    sw t0, 4(zero)
    jal zero, step_return
grow:
    lw t0, 0(zero)
    addi t0, t0, 1
    sw t0, 0(zero)
    lw t1, 28(zero)
    addi t1, t1, 1
    sw t1, 28(zero)
    lw t2, 44(zero)
    sltu t3, t2, t1
    beq t3, zero, check_win
    sw t1, 44(zero)
check_win:
    addi t1, zero, 256
    beq t0, t1, win
    jal ra, spawn_food
    jal zero, step_return
lose:
    addi t0, zero, 3
    sw t0, 24(zero)
    jal zero, step_return
win:
    addi t0, zero, 4
    sw t0, 24(zero)
    addi t0, zero, -1
    sw t0, 16(zero)
step_return:
    lw ra, 12(sp)
    addi sp, sp, 16
    jalr zero, 0(ra)

spawn_food:
    # LCG modulo 256: multiplier 5 and increment 1 visit all 256 cells.
    lw t0, 20(zero)
next_candidate:
    slli t1, t0, 2
    add t0, t0, t1
    addi t0, t0, 1
    andi t0, t0, 255
    lw t1, 4(zero)
    lw t2, 0(zero)
food_scan:
    beq t2, zero, food_found
    slli t3, t1, 2
    addi t3, t3, 256
    lw t4, 0(t3)
    beq t4, t0, next_candidate
    addi t1, t1, 1
    andi t1, t1, 255
    addi t2, t2, -1
    jal zero, food_scan
food_found:
    sw t0, 20(zero)
    sw t0, 16(zero)
    jalr zero, 0(ra)

render:
    addi sp, sp, -16
    sw ra, 12(sp)
    addi t0, zero, 1856
    addi t1, zero, 16
clear_rows:
    sw zero, 0(t0)
    addi t0, t0, 4
    addi t1, t1, -1
    bne t1, zero, clear_rows
    lw s6, 4(zero)
    lw s7, 0(zero)
draw_snake:
    slli t0, s6, 2
    addi t0, t0, 256
    lw a0, 0(t0)
    jal ra, draw_cell
    addi s6, s6, 1
    andi s6, s6, 255
    addi s7, s7, -1
    bne s7, zero, draw_snake
    lw a0, 16(zero)
    addi t0, zero, -1
    beq a0, t0, metadata
    jal ra, draw_cell
metadata:
    lw t0, 28(zero)
    sw t0, 128(s11)
    lw t0, 24(zero)
    sw t0, 132(s11)
    lw t0, 8(zero)
    slli t0, t0, 2
    addi t0, t0, 256
    lw t0, 0(t0)
    sw t0, 136(s11)
    lw t0, 16(zero)
    sw t0, 140(s11)
    lw t0, 0(zero)
    sw t0, 144(s11)
    lw t0, 44(zero)
    sw t0, 148(s11)
    lw t0, 152(s11)
    addi t0, t0, 1
    sw t0, 152(s11)
    lw ra, 12(sp)
    addi sp, sp, 16
    jalr zero, 0(ra)
draw_cell:
    andi t0, a0, 15
    slli t0, t0, 2
    addi t0, t0, 1280
    lw t1, 0(t0)
    srli t0, a0, 4
    slli t0, t0, 2
    addi t0, t0, 1856
    lw t2, 0(t0)
    or t2, t2, t1
    sw t2, 0(t0)
    jalr zero, 0(ra)
