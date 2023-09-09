`timescale 1ns/1ps

module Counter # (
    parameter WIDTH = 8
) (
    input               rst_n,  // sync reset
    input               clk,
    // Count
    output [WIDTH-1:0]  count
);

initial begin
    $display("WIDTH: %f", WIDTH);
end

// Registers and wires
reg [WIDTH-1:0] count_r;

// Combinatorial assignments
assign count = count_r;

// Sequential logic
always @(posedge clk) begin
    if (rst_n == 1'b0) begin
        count_r <= 'd0;
    end else begin
        count_r <= count_r + 'd1;
    end
end

endmodule
