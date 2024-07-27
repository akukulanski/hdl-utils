`timescale 1ns/1ps

module uart_rx #(
    parameter UART_CLK_DIV = 32
)(
    // Clock & Sync Reset
    input               clk,
    input               rst,
    // Stream Interface for received data
    output              valid,
    output [7:0]        data,
    input               ready,
    output              overflow,
    // UART Rx
    input               rx
);

localparam integer FULL_BIT_LENGTH = UART_CLK_DIV - 1;
localparam integer HALF_BIT_LENGTH = (UART_CLK_DIV >> 1);

localparam ST_IDLE = 0;
localparam ST_START_BIT = 1;
localparam ST_DATA = 2;
localparam ST_STOP_BIT = 3;
localparam N_STATES = ST_STOP_BIT + 1;

reg [$clog2(N_STATES)-1:0] state_recv = 'd0;
reg [$clog2(UART_CLK_DIV)-1:0] uart_rx_clk_counter = 'd0;
reg [2:0] bit_count = 'd0;
reg [7:0] buffer = 'd0;

reg valid_r;
reg [7:0] data_r;
reg overflow_r;

assign valid = valid_r;
assign data = data_r;
assign overflow = overflow_r;

always @(posedge clk) begin
    if (rst) begin
        state_recv <= 'd0;
        uart_rx_clk_counter <= 'd0;
        bit_count <= 'd0;
        buffer <= 'd0;
        valid_r <= 'd0;
        data_r <= 'd0;
        overflow_r <= 'd0;
    end else begin
        uart_rx_clk_counter <= uart_rx_clk_counter + 'd1;

        if (valid & ready) begin
            valid_r <= 1'b0;
            data_r <= 'd0;
        end

        // FSM recv
        case (state_recv)

            ST_IDLE:
            begin
                if (~rx) begin  // if (rx == 1'b0)
                    // neg edge -> start bit
                    uart_rx_clk_counter <= 'd0;
                    state_recv <= ST_START_BIT;
                end
            end

            ST_START_BIT:
            begin
                if (uart_rx_clk_counter == HALF_BIT_LENGTH) begin
                    if (~rx) begin
                        // still low, start reception
                        uart_rx_clk_counter <= 'd0;
                        bit_count <= 'd0;
                        buffer <= 'd0;
                        state_recv <= ST_DATA;
                    end else begin
                        // Back to high after neg edge, assume noise.
                        state_recv <= ST_IDLE;
                    end
                end
            end

            ST_DATA:
            begin
                if (uart_rx_clk_counter == FULL_BIT_LENGTH) begin
                    uart_rx_clk_counter <= 'd0;
                    buffer <= {buffer[6:0], rx};
                    bit_count <= bit_count + 'd1;
                    if (bit_count == 'd7) begin
                        state_recv <= ST_STOP_BIT;
                    end
                end
            end

            ST_STOP_BIT:
            begin
                if (uart_rx_clk_counter == FULL_BIT_LENGTH) begin
                    uart_rx_clk_counter <= 'd0;
                    if (rx) begin
                        // End
                        valid_r <= 1'b1;
                        data_r <= buffer;
                        if (valid & ~ready) begin
                            overflow_r <= 1'b1;  // NOTE: only cleared with core reset.
                        end
                    end else begin
                        // Bad stop bit. Nothing.
                    end
                    buffer <= 'd0;
                    state_recv <= ST_IDLE;
                end
            end

            default:
            begin
                state_recv <= ST_IDLE;
            end

        endcase
    end
end //end of always

// Debug

wire [31:0] full_bit_length_w;
wire [31:0] half_bit_length_w;

assign full_bit_length_w = FULL_BIT_LENGTH;
assign half_bit_length_w = HALF_BIT_LENGTH;

endmodule
