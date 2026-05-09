`define INITIALIZE_MEMORY
//`include "/users/shukir/logic_design/Project/design/work/include/rtl_paths.svh"

module top_iris_tb #()();
  
import types_pkg::*;

// parameters
localparam ADDR_WIDTH = 7;                               // Number of address bits
localparam REG_COUNT  = 1 << (ADDR_WIDTH);               // Number of control/status registers = 2^(ADDR_WIDTH)
localparam BITS_COUNT = REG_COUNT * 8;                   // Number of bits for control/status REG_COUNT * 8 (bits per register)
localparam MEM_BUFFER_SIZE = 2048;		                 // Memory buffer is 2048 words of 64 bits, each.
localparam FLOPS_BUFFER_SIZE = 128;		                 // Memory-on-Flops buffer is 128 words of 64 bits, each.
localparam FLOPS_BUFFER_SIZE_1 = FLOPS_BUFFER_SIZE - 1;
localparam MEM_BUFFER_SIZE_1 = MEM_BUFFER_SIZE - 1;

	wire clkin_p;  
	wire clkin_n;  
	wire vin_p;    
	wire vin_n;
	wire dftd;
	wire dftc;
	wire [1:0] dft;
	wire vcm;
	wire vref;

// Pads interface to the Iris chip
	wire PAD1_VSS    ;
	wire PAD4_VSS    ;
	wire PAD5_VSS    ;
	wire PAD8_VSS    ;
	wire PAD17_VSS   ;
	wire PAD9_VDDA   ;
	wire PAD26_VDDA  ;
	wire PAD10_VDDC  ;
	wire PAD14_VDDC  ;
	wire PAD23_VDDC  ;
	wire PAD24_VDDIO ;

	wire PAD2_vin_p  ;
	wire PAD3_vin_n  ;
	wire PAD6_clkin_p;
	wire PAD7_clkin_n;
	wire PAD11_vcm   ;
	wire PAD15_dfxa0 ;
	wire PAD16_dfxa1 ;
	wire PAD25_vref  ;

	wire PAD12_dftd ;
	wire PAD13_dftc ;
	wire PAD18_tdo  ;
	wire PAD19_tck  ;
	wire PAD20_tdi  ;
	wire PAD21_tms  ;
	wire PAD22_rstN ;

  int tested_buffer_size;
  int max_buffer_size;
  int flops_tests_index = 0;
  logic [63:0] write_data;
  int test_index;
  int returned_test_index;
  boolean memory_on_flops;

  logic reg_clk;		// global clock from IP (125MHz)
  logic resetN;		   	// global reset (active low at the pad)
  logic tck;     		// Test Clock
  logic tms;     		// Test Mode Select
  logic tdi;     		// Test Data In
  logic tdo;      	    // Test Data Out
  
  logic [63:0] data_in_from_ip0;
  logic [63:0] data_in_from_ip1;
  logic [63:0] data_in_from_ip2;
  logic [63:0] data_in_from_ip3;
  logic start_stop_out;
  logic [63:0] data_out_from_mem;
  
  logic [7:0] returned_data;
  logic [63:0] data_out;
  logic [MEM_BUFFER_SIZE_1:0][63:0] mem_read_buffer;
  logic [MEM_BUFFER_SIZE_1:0][63:0] mem_write_buffer;
  logic [MEM_BUFFER_SIZE_1:0] mem_results;
  logic [FLOPS_BUFFER_SIZE_1:0][63:0] flops_read_buffer;
  logic [FLOPS_BUFFER_SIZE_1:0][63:0] flops_serial_read_buffer;
  logic [FLOPS_BUFFER_SIZE_1:0][63:0] flops_write_buffer;
  logic [FLOPS_BUFFER_SIZE_1:0] flops_results;
  
  logic [10:0] partial_address;
  logic [11:0] ds_number;
  logic [2:0]  mux_index;
  logic dig_dft_out;
  logic dft_clk_out;  
  logic serial_output;
  
  int   run_buffer_size;
  int   run_buffer_size_1;
  logic [MEM_BUFFER_SIZE_1:0][63:0] read_buffer;
  logic [MEM_BUFFER_SIZE_1:0][63:0] write_buffer;
  logic [MEM_BUFFER_SIZE_1:0]       results;
  logic [MEM_BUFFER_SIZE_1:0][63:0] serial_read_buffer;

  logic [0:127][7:0] expected_data = {
	  8'b0001_0010,   // 0
	  8'b0000_0000,   // 1
	  8'b1000_0010,   // 2
	  8'b0011_0000,   // 3
	  8'b1000_0001,   // 4
	  8'b0001_0000,   // 5
	  8'b0001_0000,   // 6
	  8'b0000_0000,   // 7
	  8'b0000_0000,   // 8
	  8'b0000_0000,   // 9
	  8'b0000_0000,   // 10
	  8'b0000_0000,   // 11
	  8'b0000_0000,   // 12
	  8'b0000_0000,   // 13
	  8'b0000_0000,   // 14
	  8'b0000_0000,   // 15
	  8'b0000_0000,   // 16
	  8'b0000_0000,   // 17
	  8'b0000_0000,   // 18
	  8'b0000_0000,   // 19
	  8'b0000_0000,   // 20
	  8'b0000_0000,   // 21
	  8'b0000_0000,   // 22
	  8'b0000_0000,   // 23
	  8'b0000_0000,   // 24
	  8'b0000_0000,   // 25
	  8'b0000_0000,   // 26
	  8'b1111_1111,   // 27
	  8'b0000_0001,   // 28
	  8'b0000_0000,   // 29
	  8'b0000_0000,   // 30
	  8'b1111_1111,   // 31
	  8'b0000_0001,   // 32
	  8'b0000_0000,   // 33
	  8'b0000_0000,   // 34
	  8'b1000_0000,   // 35
	  8'b0000_0000,   // 36
	  8'b0000_0000,   // 37
	  8'b0000_0000,   // 38
	  8'b0000_0000,   // 39
	  8'b0000_0001,   // 40
	  8'b1000_0000,   // 41
	  8'b0000_0000,   // 42
	  8'b0000_0000,   // 43
	  8'b0000_0000,   // 44
	  8'b0000_0000,   // 45
	  8'b0000_0001,   // 46
	  8'b0111_1011,   // 47
	  8'b0000_1110,   // 48
	  8'b0000_0000,   // 49
	  8'b0000_0000,   // 50
	  8'b0011_0011,   // 51
	  8'b0011_0011,   // 52
	  8'b0000_0000,   // 53
	  8'b0000_0000,   // 54
	  8'b1111_1111,   // 55
	  8'b0000_1111,   // 56
	  8'b0110_0110,   // 57
	  8'b1001_1010,   // 58
	  8'b0000_0111,   // 59
	  8'b0000_0000,   // 60
	  8'b0000_0000,   // 61
	  8'b1111_1111,   // 62
	  8'b0000_1111,   // 63
	  8'b0110_0110,   // 64
	  8'b1001_1010,   // 65
	  8'b0000_0111,   // 66
	  8'b0000_0000,   // 67
	  8'b0000_0000,   // 68
	  8'b0000_0000,   // 69
	  8'b0000_0000,   // 70
	  8'b0000_0000,   // 71
	  8'b0000_0000,   // 72
	  8'b0000_0000,   // 73
	  8'b0000_0000,   // 74
	  8'b0000_0000,   // 75
	  8'b0000_0000,   // 76
	  8'b0000_0000,   // 77
	  8'b0000_0000,   // 78
	  8'b0000_0000,   // 79
	  8'b0000_0000,   // 80
	  8'b0000_0000,   // 81
	  8'b0000_0000,   // 82
	  8'b0000_0000,   // 83
	  8'b0000_0000,   // 84
	  8'b0000_0000,   // 85
	  8'b0000_0000,   // 86
	  8'b0000_0000,   // 87
	  8'b0000_0000,   // 88
	  8'b0000_0000,   // 89
	  8'b0000_0000,   // 90
	  8'b0000_0000,   // 91
	  8'b0000_0000,   // 92
	  8'b0000_0000,   // 93
	  8'b0000_0000,   // 94
	  8'b0000_0000,   // 95
	  8'b0000_0000,   // 96
	  8'b0000_0000,   // 97
	  8'b0000_0000,   // 98
	  8'b0000_0000,   // 99
	  8'b0000_0000,   // 100
	  8'b0000_0000,   // 101
	  8'b0000_0000,   // 102
	  8'b0000_0000,   // 103
	  8'b0000_0000,   // 104
	  8'b0000_0000,   // 105
	  8'b0000_0000,   // 106
	  8'b0000_0000,   // 107
	  8'b0000_0000,   // 108
	  8'b0000_0000,   // 109
	  8'b0000_0000,   // 110
	  8'b0000_0000,   // 111
	  8'b0000_0000,   // 112
	  8'b0000_0000,   // 113
	  8'b0000_0000,   // 114
	  8'b0000_0000,   // 115
	  8'b0000_0000,   // 116
	  8'b0000_0000,   // 117
	  8'b0000_0000,   // 118
	  8'b0000_0000,   // 119
	  8'b0000_0000,   // 120
	  8'b0000_0000,   // 121
	  8'b0000_0000,   // 122
	  8'b0000_0000,   // 123
	  8'b0000_0000,   // 124
	  8'b0000_0000,   // 125
	  8'b0000_0000,   // 126
	  8'b0000_0000    // 127
  };

  typedef enum logic [3:0] {
	  STATUS_READ	   = 4'b0000,
	  STATUS_WRITE	   = 4'b0001,
	  CONTROL_READ	   = 4'b0100,
	  CONTROL_WRITE	   = 4'b0101,
	  MEMORY_READ	   = 4'b1000,
	  MEMORY_WRITE	   = 4'b1001
  } cmd_state_t;

  cmd_state_t cmd;

`include "/users/epstmh/Project_B/rev12/functions/fc_function12.sv"
`include "/users/epstmh/Project_B/rev12/functions/tests_separate/tests_include.sv"

  top_iris #(
	  .ADDR_WIDTH (ADDR_WIDTH),
	  .REG_COUNT  (REG_COUNT ),
	  .BITS_COUNT (BITS_COUNT)
	  ) uut (
`ifdef VALIDATION
  .reg_clk(reg_clk),
  .tdo_core(tdo),
  .data_from_mem(data_out_from_mem),
  .data_in_from_ip0(data_in_from_ip0),
  .data_in_from_ip1(data_in_from_ip1),
  .data_in_from_ip2(data_in_from_ip2),
  .data_in_from_ip3(data_in_from_ip3),
  .start_stop_out(start_stop_out),
`endif
  .PAD1_VSS    (PAD1_VSS    ),
  .PAD2_vin_p  (PAD2_vin_p  ),
  .PAD3_vin_n  (PAD3_vin_n  ),
  .PAD4_VSS    (PAD4_VSS    ),
  .PAD5_VSS    (PAD5_VSS    ),
  .PAD6_clkin_p(PAD6_clkin_p),
  .PAD7_clkin_n(PAD7_clkin_n),
  .PAD8_VSS    (PAD8_VSS    ),
  .PAD9_VDDA   (PAD9_VDDA   ),
  .PAD10_VDDC  (PAD10_VDDC  ),
  .PAD11_vcm   (PAD11_vcm   ),
  .PAD12_dftd  (PAD12_dftd  ),
  .PAD13_dftc  (PAD13_dftc  ),
  .PAD14_VDDC  (PAD14_VDDC  ),
  .PAD15_dfxa0 (PAD15_dfxa0 ),
  .PAD16_dfxa1 (PAD16_dfxa1 ),
  .PAD17_VSS   (PAD17_VSS   ),
  .PAD18_tdo   (PAD18_tdo   ),
  .PAD19_tck   (PAD19_tck   ),
  .PAD20_tdi   (PAD20_tdi   ),
  .PAD21_tms   (PAD21_tms   ),
  .PAD22_rstN  (PAD22_rstN  ),
  .PAD23_VDDC  (PAD23_VDDC  ),
  .PAD24_VDDIO (PAD24_VDDIO ),
  .PAD25_vref  (PAD25_vref  ),
  .PAD26_VDDA  (PAD26_VDDA  )
  );

  assign  PAD1_VSS     = 1'b0;
  assign  PAD4_VSS     = 1'b0;
  assign  PAD5_VSS     = 1'b0;
  assign  PAD8_VSS     = 1'b0;
  assign  PAD17_VSS    = 1'b0;
  assign  PAD9_VDDA    = 1'b1;
  assign  PAD26_VDDA   = 1'b1;
  assign  PAD10_VDDC   = 1'b1;
  assign  PAD14_VDDC   = 1'b1;
  assign  PAD23_VDDC   = 1'b1;
  assign  PAD24_VDDIO  = 1'b1;
  
  assign  PAD2_vin_p   = vin_p  ;
  assign  PAD3_vin_n   = vin_n  ;
  assign  PAD6_clkin_p = clkin_p;
  assign  PAD7_clkin_n = clkin_n;
  assign  PAD11_vcm    = vcm    ;
  assign  PAD15_dfxa0  = dft[0] ;
  assign  PAD16_dfxa1  = dft[1] ;
  assign  PAD25_vref   = vref   ;
  
  assign  PAD18_tdo    = tdo   ;
  assign  PAD19_tck    = tck   ;
  assign  PAD20_tdi    = tdi   ;
  assign  PAD21_tms    = tms   ;
  assign  PAD22_rstN   = resetN;
  
  assign serial_output = PAD12_dftd;
  assign dft_clk_out   = PAD13_dftc;

  // TCK clock generation (10ns period = 100MHz)
  always begin
    #5 tck = ~tck;
  end

  initial begin
	$display("=== Starting Simulation ===");
	tck    = 0;
	tms    = 1;
	tdi    = 0;
	resetN = 0;
	#20;

	// Reset TAP (5 TCK with TMS=1)
	repeat (5) begin
	  @(negedge tck);
	  tms = 1;
	end

	#10 resetN = 1;


	//*****************************************************************//
	//*** Standalone Tests ********************************************//
	//*****************************************************************//

	// Test No. 1
	check_serial_output_po(FALSE);

	// Test No. 2
	read_all_control_registers_po_values(returned_data, expected_data, FALSE);

	// Test No. 3
	write_read_all_control_registers(returned_data, FALSE);

	// Test No. 4
	read_all_control_registers(returned_data, FALSE);

	// Test No. 5
	masked_write_read_all_control_registers(returned_data, FALSE);

	// Test No. 6
	write_read_all_status_registers(returned_data, FALSE);

	// Test No. 7
	read_all_status_registers(returned_data, FALSE);

	#200 $finish;
  end

endmodule

