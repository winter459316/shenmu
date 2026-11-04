
################################################################
# This is a generated script based on design: system
#
# Though there are limitations about the generated script,
# the main purpose of this utility is to make learning
# IP Integrator Tcl commands easier.
################################################################

namespace eval _tcl {
proc get_script_folder {} {
   set script_path [file normalize [info script]]
   set script_folder [file dirname $script_path]
   return $script_folder
}
}
variable script_folder
set script_folder [_tcl::get_script_folder]

################################################################
# Check if script is running in correct Vivado version.
################################################################
set scripts_vivado_version 2018.2
set current_vivado_version [version -short]

if { [string first $scripts_vivado_version $current_vivado_version] == -1 } {
   puts ""
   catch {common::send_msg_id "BD_TCL-109" "ERROR" "This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Please run the script in Vivado <$scripts_vivado_version> then open the design in Vivado <$current_vivado_version>. Upgrade the design by running \"Tools => Report => Report IP Status...\", then run write_bd_tcl to create an updated script."}

   return 1
}

################################################################
# START
################################################################

# To test this script, run the following commands from Vivado Tcl console:
# source system_script.tcl


# The design that will be created by this Tcl script contains the following 
# module references:
# video_clock_tree, usb_pl_keys

# Please add the sources of those modules before sourcing this Tcl script.

# If there is no project opened, this script will create a
# project, but make sure you do not have an existing project
# <./myproj/project_1.xpr> in the current working folder.

set list_projs [get_projects -quiet]
if { $list_projs eq "" } {
   create_project project_1 myproj -part xczu4ev-sfvc784-2-i
}


# CHANGE DESIGN NAME HERE
variable design_name
set design_name system

# If you do not already have an existing IP Integrator design open,
# you can create a design using the following command:
#    create_bd_design $design_name

# Creating design if needed
set errMsg ""
set nRet 0

set cur_design [current_bd_design -quiet]
set list_cells [get_bd_cells -quiet]

if { ${design_name} eq "" } {
   # USE CASES:
   #    1) Design_name not set

   set errMsg "Please set the variable <design_name> to a non-empty value."
   set nRet 1

} elseif { ${cur_design} ne "" && ${list_cells} eq "" } {
   # USE CASES:
   #    2): Current design opened AND is empty AND names same.
   #    3): Current design opened AND is empty AND names diff; design_name NOT in project.
   #    4): Current design opened AND is empty AND names diff; design_name exists in project.

   if { $cur_design ne $design_name } {
      common::send_msg_id "BD_TCL-001" "INFO" "Changing value of <design_name> from <$design_name> to <$cur_design> since current design is empty."
      set design_name [get_property NAME $cur_design]
   }
   common::send_msg_id "BD_TCL-002" "INFO" "Constructing design in IPI design <$cur_design>..."

} elseif { ${cur_design} ne "" && $list_cells ne "" && $cur_design eq $design_name } {
   # USE CASES:
   #    5) Current design opened AND has components AND same names.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 1
} elseif { [get_files -quiet ${design_name}.bd] ne "" } {
   # USE CASES: 
   #    6) Current opened design, has components, but diff names, design_name exists in project.
   #    7) No opened design, design_name exists in project.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 2

} else {
   # USE CASES:
   #    8) No opened design, design_name not in project.
   #    9) Current opened design, has components, but diff names, design_name not in project.

   common::send_msg_id "BD_TCL-003" "INFO" "Currently there is no design <$design_name> in project, so creating one..."

   create_bd_design $design_name

   common::send_msg_id "BD_TCL-004" "INFO" "Making design <$design_name> as current_bd_design."
   current_bd_design $design_name

}

common::send_msg_id "BD_TCL-005" "INFO" "Currently the variable <design_name> is equal to \"$design_name\"."

if { $nRet != 0 } {
   catch {common::send_msg_id "BD_TCL-114" "ERROR" $errMsg}
   return $nRet
}

set bCheckIPsPassed 1
##################################################################
# CHECK IPs
##################################################################
set bCheckIPs 1
if { $bCheckIPs == 1 } {
   set list_check_ips "\ 
xilinx.com:ip:clk_wiz:6.0\
xilinx.com:ip:proc_sys_reset:5.0\
shenmu.local:stereo:fast_deconv:1.6\
openedv.com:user:DVI_Transmitter:1.0\
shenmu.local:stereo:usb_image_features:2.0\
shenmu.local:stereo:mixed_conv:1.2\
xilinx.com:ip:xlconstant:1.1\
xilinx.com:ip:zynq_ultra_ps_e:3.2\
xilinx.com:ip:axi_vdma:6.3\
xilinx.com:ip:v_axi4s_vid_out:4.0\
xilinx.com:ip:v_tc:6.1\
"

   set list_ips_missing ""
   common::send_msg_id "BD_TCL-006" "INFO" "Checking if the following IPs exist in the project's IP catalog: $list_check_ips ."

   foreach ip_vlnv $list_check_ips {
      set ip_obj [get_ipdefs -all $ip_vlnv]
      if { $ip_obj eq "" } {
         lappend list_ips_missing $ip_vlnv
      }
   }

   if { $list_ips_missing ne "" } {
      catch {common::send_msg_id "BD_TCL-115" "ERROR" "The following IPs are not found in the IP Catalog:\n  $list_ips_missing\n\nResolution: Please add the repository containing the IP(s) to the project." }
      set bCheckIPsPassed 0
   }

}

##################################################################
# CHECK Modules
##################################################################
set bCheckModules 1
if { $bCheckModules == 1 } {
   set list_check_mods "\ 
video_clock_tree\
usb_pl_keys\
"

   set list_mods_missing ""
   common::send_msg_id "BD_TCL-006" "INFO" "Checking if the following modules exist in the project's sources: $list_check_mods ."

   foreach mod_vlnv $list_check_mods {
      if { [can_resolve_reference $mod_vlnv] == 0 } {
         lappend list_mods_missing $mod_vlnv
      }
   }

   if { $list_mods_missing ne "" } {
      catch {common::send_msg_id "BD_TCL-115" "ERROR" "The following module(s) are not found in the project: $list_mods_missing" }
      common::send_msg_id "BD_TCL-008" "INFO" "Please add source files for the missing module(s) above."
      set bCheckIPsPassed 0
   }
}

if { $bCheckIPsPassed != 1 } {
  common::send_msg_id "BD_TCL-1003" "WARNING" "Will not continue with creation of design due to the error(s) above."
  return 3
}

##################################################################
# DESIGN PROCs
##################################################################



# Procedure to create entire design; Provide argument to make
# procedure reusable. If parentCell is "", will use root.
proc create_root_design { parentCell } {

  variable script_folder
  variable design_name

  if { $parentCell eq "" } {
     set parentCell [get_bd_cells /]
  }

  # Get object for parentCell
  set parentObj [get_bd_cells $parentCell]
  if { $parentObj == "" } {
     catch {common::send_msg_id "BD_TCL-100" "ERROR" "Unable to find parent cell <$parentCell>!"}
     return
  }

  # Make sure parentObj is hier blk
  set parentType [get_property TYPE $parentObj]
  if { $parentType ne "hier" } {
     catch {common::send_msg_id "BD_TCL-101" "ERROR" "Parent <$parentObj> has TYPE = <$parentType>. Expected to be <hier>."}
     return
  }

  # Save current instance; Restore later
  set oldCurInst [current_bd_instance .]

  # Set parent object as current
  current_bd_instance $parentObj


  # Create interface ports
  set TMDS [ create_bd_intf_port -mode Master -vlnv openedv.com:user:TMDS_rtl:1.0 TMDS ]

  # Create ports
  set pl_key1_n [ create_bd_port -dir I pl_key1_n ]
  set pl_key2_n [ create_bd_port -dir I pl_key2_n ]

  # Create instance: compute_clock, and set properties
  set compute_clock [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 compute_clock ]
  set_property -dict [ list \
   CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {115.000} \
   CONFIG.PRIM_IN_FREQ {99.999999} \
   CONFIG.RESET_TYPE {ACTIVE_HIGH} \
   CONFIG.USE_LOCKED {true} \
   CONFIG.USE_RESET {true} \
 ] $compute_clock

  # Create instance: compute_reset, and set properties
  set compute_reset [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 compute_reset ]

  # Create instance: control, and set properties
  set control [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 control ]
  set_property -dict [ list \
   CONFIG.NUM_MI {5} \
 ] $control

  # Create instance: ddr, and set properties
  set ddr [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ddr ]
  set_property -dict [ list \
   CONFIG.NUM_MI {1} \
   CONFIG.NUM_SI {6} \
 ] $ddr

  # Create instance: fast_deconv, and set properties
  set fast_deconv [ create_bd_cell -type ip -vlnv shenmu.local:stereo:fast_deconv:1.6 fast_deconv ]
  set_property -dict [ list \
   CONFIG.C_M_AXI_DDR_DATA_WIDTH {512} \
   CONFIG.C_M_AXI_RESULT_DDR_DATA_WIDTH {512} \
 ] $fast_deconv

  # Create instance: hdmi_clocks, and set properties
  set block_name video_clock_tree
  set block_cell_name hdmi_clocks
  if { [catch {set hdmi_clocks [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_msg_id "BD_TCL-105" "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $hdmi_clocks eq "" } {
     catch {common::send_msg_id "BD_TCL-106" "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: hdmi_tx, and set properties
  set hdmi_tx [ create_bd_cell -type ip -vlnv openedv.com:user:DVI_Transmitter:1.0 hdmi_tx ]

  # Create instance: images, and set properties
  set images [ create_bd_cell -type ip -vlnv shenmu.local:stereo:usb_image_features:2.0 images ]

  # Create instance: mixed_conv, and set properties
  set mixed_conv [ create_bd_cell -type ip -vlnv shenmu.local:stereo:mixed_conv:1.2 mixed_conv ]

  # Create instance: one, and set properties
  set one [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {1} \
 ] $one

  # Create instance: pl_keys, and set properties
  set block_name usb_pl_keys
  set block_cell_name pl_keys
  if { [catch {set pl_keys [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_msg_id "BD_TCL-105" "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $pl_keys eq "" } {
     catch {common::send_msg_id "BD_TCL-106" "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: ps, and set properties
  set ps [ create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.2 ps ]
  set_property -dict [ list \
   CONFIG.PSU_DDR_RAM_HIGHADDR {0x7FFFFFFF} \
   CONFIG.PSU_DDR_RAM_HIGHADDR_OFFSET {0x00000002} \
   CONFIG.PSU_DDR_RAM_LOWADDR_OFFSET {0x80000000} \
   CONFIG.PSU__ACT_DDR_FREQ_MHZ {799.992004} \
   CONFIG.PSU__CRF_APB__ACPU_CTRL__ACT_FREQMHZ {1333.333320} \
   CONFIG.PSU__CRF_APB__ACPU_CTRL__DIVISOR0 {1} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__FBDIV {80} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__FRACDATA {0} \
   CONFIG.PSU__CRF_APB__APLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRF_APB__APLL_TO_LPD_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__ACT_FREQMHZ {249.999998} \
   CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DBG_TRACE_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__ACT_FREQMHZ {249.999998} \
   CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DDR_CTRL__ACT_FREQMHZ {399.999996} \
   CONFIG.PSU__CRF_APB__DDR_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__ACT_FREQMHZ {599.999994} \
   CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__FBDIV {72} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__FRACDATA {0} \
   CONFIG.PSU__CRF_APB__DPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRF_APB__DPLL_TO_LPD_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRF_APB__DP_AUDIO_REF_CTRL__DIVISOR0 {63} \
   CONFIG.PSU__CRF_APB__DP_AUDIO_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRF_APB__DP_STC_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRF_APB__DP_STC_REF_CTRL__DIVISOR1 {10} \
   CONFIG.PSU__CRF_APB__DP_VIDEO_REF_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__DP_VIDEO_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__ACT_FREQMHZ {599.999994} \
   CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__GPU_REF_CTRL__ACT_FREQMHZ {599.999994} \
   CONFIG.PSU__CRF_APB__GPU_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__PCIE_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRF_APB__SATA_REF_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__ACT_FREQMHZ {99.999999} \
   CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__ACT_FREQMHZ {533.333328} \
   CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__FBDIV {64} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__FRACDATA {0} \
   CONFIG.PSU__CRF_APB__VPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRF_APB__VPLL_TO_LPD_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__ACT_FREQMHZ {533.333328} \
   CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRL_APB__AFI6_REF_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__AMS_REF_CTRL__ACT_FREQMHZ {50.000000} \
   CONFIG.PSU__CRL_APB__AMS_REF_CTRL__DIVISOR0 {20} \
   CONFIG.PSU__CRL_APB__AMS_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__CAN0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__CAN0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__CAN1_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__CAN1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__CPU_R5_CTRL__ACT_FREQMHZ {533.333328} \
   CONFIG.PSU__CRL_APB__CPU_R5_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__ACT_FREQMHZ {249.999998} \
   CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__DLL_REF_CTRL__ACT_FREQMHZ {999.999990} \
   CONFIG.PSU__CRL_APB__GEM0_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM1_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM2_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM2_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM_TSU_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__GEM_TSU_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__FBDIV {60} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__FRACDATA {0} \
   CONFIG.PSU__CRL_APB__IOPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRL_APB__IOPLL_TO_FPD_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__ACT_FREQMHZ {266.666664} \
   CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__ACT_FREQMHZ {99.999999} \
   CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__DIVISOR0 {10} \
   CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__ACT_FREQMHZ {533.333328} \
   CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRL_APB__NAND_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__NAND_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PCAP_CTRL__ACT_FREQMHZ {199.999998} \
   CONFIG.PSU__CRL_APB__PCAP_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__ACT_FREQMHZ {99.999999} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__DIVISOR0 {10} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__PL1_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__PL1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PL2_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__PL2_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PL3_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__PL3_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__FBDIV {64} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__FRACDATA {0} \
   CONFIG.PSU__CRL_APB__RPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRL_APB__RPLL_TO_FPD_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRL_APB__SDIO0_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SDIO0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__SPI0_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SPI0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__SPI1_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SPI1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__ACT_FREQMHZ {33.333333} \
   CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__DIVISOR0 {1} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__UART1_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__UART1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__USB1_BUS_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__USB1_BUS_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__DIVISOR1 {15} \
   CONFIG.PSU__DDR_HIGH_ADDRESS_GUI_ENABLE {0} \
   CONFIG.PSU__FPGA_PL0_ENABLE {1} \
   CONFIG.PSU__GPIO_EMIO_WIDTH {10} \
   CONFIG.PSU__GPIO_EMIO__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__GPIO_EMIO__PERIPHERAL__IO {10} \
   CONFIG.PSU__MAXIGP0__DATA_WIDTH {128} \
   CONFIG.PSU__MAXIGP2__DATA_WIDTH {32} \
   CONFIG.PSU__OVERRIDE__BASIC_CLOCK {1} \
   CONFIG.PSU__PL_CLK0_BUF {TRUE} \
   CONFIG.PSU__PROTECTION__MASTERS {USB1:NonSecure;0|USB0:NonSecure;0|S_AXI_LPD:NA;0|S_AXI_HPC1_FPD:NA;0|S_AXI_HPC0_FPD:NA;0|S_AXI_HP3_FPD:NA;0|S_AXI_HP2_FPD:NA;1|S_AXI_HP1_FPD:NA;0|S_AXI_HP0_FPD:NA;0|S_AXI_ACP:NA;0|S_AXI_ACE:NA;0|SD1:NonSecure;0|SD0:NonSecure;0|SATA1:NonSecure;0|SATA0:NonSecure;0|RPU1:Secure;1|RPU0:Secure;1|QSPI:NonSecure;0|PMU:NA;1|PCIe:NonSecure;0|NAND:NonSecure;0|LDMA:NonSecure;1|GPU:NonSecure;1|GEM3:NonSecure;0|GEM2:NonSecure;0|GEM1:NonSecure;0|GEM0:NonSecure;0|FDMA:NonSecure;1|DP:NonSecure;0|DAP:NA;1|Coresight:NA;1|CSU:NA;1|APU:NA;1} \
   CONFIG.PSU__PROTECTION__SLAVES {LPD;USB3_1_XHCI;FE300000;FE3FFFFF;0|LPD;USB3_1;FF9E0000;FF9EFFFF;0|LPD;USB3_0_XHCI;FE200000;FE2FFFFF;0|LPD;USB3_0;FF9D0000;FF9DFFFF;0|LPD;UART1;FF010000;FF01FFFF;0|LPD;UART0;FF000000;FF00FFFF;0|LPD;TTC3;FF140000;FF14FFFF;0|LPD;TTC2;FF130000;FF13FFFF;0|LPD;TTC1;FF120000;FF12FFFF;0|LPD;TTC0;FF110000;FF11FFFF;0|FPD;SWDT1;FD4D0000;FD4DFFFF;0|LPD;SWDT0;FF150000;FF15FFFF;0|LPD;SPI1;FF050000;FF05FFFF;0|LPD;SPI0;FF040000;FF04FFFF;0|FPD;SMMU_REG;FD5F0000;FD5FFFFF;1|FPD;SMMU;FD800000;FDFFFFFF;1|FPD;SIOU;FD3D0000;FD3DFFFF;1|FPD;SERDES;FD400000;FD47FFFF;1|LPD;SD1;FF170000;FF17FFFF;0|LPD;SD0;FF160000;FF16FFFF;0|FPD;SATA;FD0C0000;FD0CFFFF;0|LPD;RTC;FFA60000;FFA6FFFF;1|LPD;RSA_CORE;FFCE0000;FFCEFFFF;1|LPD;RPU;FF9A0000;FF9AFFFF;1|FPD;RCPU_GIC;F9000000;F900FFFF;1|LPD;R5_TCM_RAM_GLOBAL;FFE00000;FFE3FFFF;1|LPD;R5_1_Instruction_Cache;FFEC0000;FFECFFFF;1|LPD;R5_1_Data_Cache;FFED0000;FFEDFFFF;1|LPD;R5_1_BTCM_GLOBAL;FFEB0000;FFEBFFFF;1|LPD;R5_1_ATCM_GLOBAL;FFE90000;FFE9FFFF;1|LPD;R5_0_Instruction_Cache;FFE40000;FFE4FFFF;1|LPD;R5_0_Data_Cache;FFE50000;FFE5FFFF;1|LPD;R5_0_BTCM_GLOBAL;FFE20000;FFE2FFFF;1|LPD;R5_0_ATCM_GLOBAL;FFE00000;FFE0FFFF;1|LPD;QSPI_Linear_Address;C0000000;DFFFFFFF;1|LPD;QSPI;FF0F0000;FF0FFFFF;0|LPD;PMU_RAM;FFDC0000;FFDDFFFF;1|LPD;PMU_GLOBAL;FFD80000;FFDBFFFF;1|FPD;PCIE_MAIN;FD0E0000;FD0EFFFF;0|FPD;PCIE_LOW;E0000000;EFFFFFFF;0|FPD;PCIE_HIGH2;8000000000;BFFFFFFFFF;0|FPD;PCIE_HIGH1;600000000;7FFFFFFFF;0|FPD;PCIE_DMA;FD0F0000;FD0FFFFF;0|FPD;PCIE_ATTRIB;FD480000;FD48FFFF;0|LPD;OCM_XMPU_CFG;FFA70000;FFA7FFFF;1|LPD;OCM_SLCR;FF960000;FF96FFFF;1|OCM;OCM;FFFC0000;FFFFFFFF;1|LPD;NAND;FF100000;FF10FFFF;0|LPD;MBISTJTAG;FFCF0000;FFCFFFFF;1|LPD;LPD_XPPU_SINK;FF9C0000;FF9CFFFF;1|LPD;LPD_XPPU;FF980000;FF98FFFF;1|LPD;LPD_SLCR_SECURE;FF4B0000;FF4DFFFF;1|LPD;LPD_SLCR;FF410000;FF4AFFFF;1|LPD;LPD_GPV;FE100000;FE1FFFFF;1|LPD;LPD_DMA_7;FFAF0000;FFAFFFFF;1|LPD;LPD_DMA_6;FFAE0000;FFAEFFFF;1|LPD;LPD_DMA_5;FFAD0000;FFADFFFF;1|LPD;LPD_DMA_4;FFAC0000;FFACFFFF;1|LPD;LPD_DMA_3;FFAB0000;FFABFFFF;1|LPD;LPD_DMA_2;FFAA0000;FFAAFFFF;1|LPD;LPD_DMA_1;FFA90000;FFA9FFFF;1|LPD;LPD_DMA_0;FFA80000;FFA8FFFF;1|LPD;IPI_CTRL;FF380000;FF3FFFFF;1|LPD;IOU_SLCR;FF180000;FF23FFFF;1|LPD;IOU_SECURE_SLCR;FF240000;FF24FFFF;1|LPD;IOU_SCNTRS;FF260000;FF26FFFF;1|LPD;IOU_SCNTR;FF250000;FF25FFFF;1|LPD;IOU_GPV;FE000000;FE0FFFFF;1|LPD;I2C1;FF030000;FF03FFFF;0|LPD;I2C0;FF020000;FF02FFFF;0|FPD;GPU;FD4B0000;FD4BFFFF;1|LPD;GPIO;FF0A0000;FF0AFFFF;1|LPD;GEM3;FF0E0000;FF0EFFFF;0|LPD;GEM2;FF0D0000;FF0DFFFF;0|LPD;GEM1;FF0C0000;FF0CFFFF;0|LPD;GEM0;FF0B0000;FF0BFFFF;0|FPD;FPD_XMPU_SINK;FD4F0000;FD4FFFFF;1|FPD;FPD_XMPU_CFG;FD5D0000;FD5DFFFF;1|FPD;FPD_SLCR_SECURE;FD690000;FD6CFFFF;1|FPD;FPD_SLCR;FD610000;FD68FFFF;1|FPD;FPD_GPV;FD700000;FD7FFFFF;1|FPD;FPD_DMA_CH7;FD570000;FD57FFFF;1|FPD;FPD_DMA_CH6;FD560000;FD56FFFF;1|FPD;FPD_DMA_CH5;FD550000;FD55FFFF;1|FPD;FPD_DMA_CH4;FD540000;FD54FFFF;1|FPD;FPD_DMA_CH3;FD530000;FD53FFFF;1|FPD;FPD_DMA_CH2;FD520000;FD52FFFF;1|FPD;FPD_DMA_CH1;FD510000;FD51FFFF;1|FPD;FPD_DMA_CH0;FD500000;FD50FFFF;1|LPD;EFUSE;FFCC0000;FFCCFFFF;1|FPD;Display Port;FD4A0000;FD4AFFFF;0|FPD;DPDMA;FD4C0000;FD4CFFFF;0|FPD;DDR_XMPU5_CFG;FD050000;FD05FFFF;1|FPD;DDR_XMPU4_CFG;FD040000;FD04FFFF;1|FPD;DDR_XMPU3_CFG;FD030000;FD03FFFF;1|FPD;DDR_XMPU2_CFG;FD020000;FD02FFFF;1|FPD;DDR_XMPU1_CFG;FD010000;FD01FFFF;1|FPD;DDR_XMPU0_CFG;FD000000;FD00FFFF;1|FPD;DDR_QOS_CTRL;FD090000;FD09FFFF;1|FPD;DDR_PHY;FD080000;FD08FFFF;1|DDR;DDR_LOW;0;7FFFFFFF;1|DDR;DDR_HIGH;800000000;800000000;0|FPD;DDDR_CTRL;FD070000;FD070FFF;1|LPD;Coresight;FE800000;FEFFFFFF;1|LPD;CSU_DMA;FFC80000;FFC9FFFF;1|LPD;CSU;FFCA0000;FFCAFFFF;0|LPD;CRL_APB;FF5E0000;FF85FFFF;1|FPD;CRF_APB;FD1A0000;FD2DFFFF;1|FPD;CCI_REG;FD5E0000;FD5EFFFF;1|FPD;CCI_GPV;FD6E0000;FD6EFFFF;1|LPD;CAN1;FF070000;FF07FFFF;0|LPD;CAN0;FF060000;FF06FFFF;0|FPD;APU;FD5C0000;FD5CFFFF;1|LPD;APM_INTC_IOU;FFA20000;FFA2FFFF;1|LPD;APM_FPD_LPD;FFA30000;FFA3FFFF;1|FPD;APM_5;FD490000;FD49FFFF;1|FPD;APM_0;FD0B0000;FD0BFFFF;1|LPD;APM2;FFA10000;FFA1FFFF;1|LPD;APM1;FFA00000;FFA0FFFF;1|LPD;AMS;FFA50000;FFA5FFFF;1|FPD;AFI_5;FD3B0000;FD3BFFFF;1|FPD;AFI_4;FD3A0000;FD3AFFFF;1|FPD;AFI_3;FD390000;FD39FFFF;1|FPD;AFI_2;FD380000;FD38FFFF;1|FPD;AFI_1;FD370000;FD37FFFF;1|FPD;AFI_0;FD360000;FD36FFFF;1|LPD;AFIFM6;FF9B0000;FF9BFFFF;1|FPD;ACPU_GIC;F9000000;F907FFFF;1} \
   CONFIG.PSU__PSS_REF_CLK__FREQMHZ {33.333333} \
   CONFIG.PSU__SAXIGP4__DATA_WIDTH {128} \
   CONFIG.PSU__USE__M_AXI_GP0 {1} \
   CONFIG.PSU__USE__M_AXI_GP1 {0} \
   CONFIG.PSU__USE__M_AXI_GP2 {0} \
   CONFIG.PSU__USE__S_AXI_GP4 {1} \
 ] $ps

  # Create instance: rst, and set properties
  set rst [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst ]

  # Create instance: video_dma, and set properties
  set video_dma [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 video_dma ]
  set_property -dict [ list \
   CONFIG.c_include_mm2s_dre {1} \
   CONFIG.c_include_s2mm {0} \
   CONFIG.c_m_axi_mm2s_data_width {128} \
   CONFIG.c_m_axis_mm2s_tdata_width {24} \
   CONFIG.c_mm2s_genlock_mode {0} \
   CONFIG.c_mm2s_linebuffer_depth {2048} \
   CONFIG.c_mm2s_max_burst_length {64} \
   CONFIG.c_num_fstores {2} \
 ] $video_dma

  # Create instance: video_mmcm, and set properties
  set video_mmcm [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 video_mmcm ]
  set_property -dict [ list \
   CONFIG.CLKOUT1_DRIVES {No_buffer} \
   CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {375} \
   CONFIG.PRIM_IN_FREQ {99.999999} \
   CONFIG.PRIM_SOURCE {No_buffer} \
   CONFIG.USE_PHASE_ALIGNMENT {false} \
 ] $video_mmcm

  # Create instance: video_out, and set properties
  set video_out [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:4.0 video_out ]
  set_property -dict [ list \
   CONFIG.C_HAS_ASYNC_CLK {1} \
 ] $video_out

  # Create instance: video_reset, and set properties
  set video_reset [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 video_reset ]

  # Create instance: video_timing, and set properties
  set video_timing [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.1 video_timing ]
  set_property -dict [ list \
   CONFIG.enable_detection {false} \
 ] $video_timing

  # Create interface connections
  connect_bd_intf_net -intf_net control_M00_AXI [get_bd_intf_pins control/M00_AXI] [get_bd_intf_pins images/s_axi_control]
  connect_bd_intf_net -intf_net control_M01_AXI [get_bd_intf_pins control/M01_AXI] [get_bd_intf_pins video_dma/S_AXI_LITE]
  connect_bd_intf_net -intf_net control_M02_AXI [get_bd_intf_pins control/M02_AXI] [get_bd_intf_pins video_timing/ctrl]
  connect_bd_intf_net -intf_net control_M03_AXI [get_bd_intf_pins control/M03_AXI] [get_bd_intf_pins fast_deconv/s_axi_control]
  connect_bd_intf_net -intf_net control_M04_AXI [get_bd_intf_pins control/M04_AXI] [get_bd_intf_pins mixed_conv/s_axi_control]
  connect_bd_intf_net -intf_net ddr_M00_AXI [get_bd_intf_pins ddr/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP2_FPD]
  connect_bd_intf_net -intf_net fast_deconv_m_axi_ddr [get_bd_intf_pins ddr/S02_AXI] [get_bd_intf_pins fast_deconv/m_axi_ddr]
  connect_bd_intf_net -intf_net fast_deconv_m_axi_result_ddr [get_bd_intf_pins ddr/S03_AXI] [get_bd_intf_pins fast_deconv/m_axi_result_ddr]
  connect_bd_intf_net -intf_net hdmi_tx_TMDS [get_bd_intf_ports TMDS] [get_bd_intf_pins hdmi_tx/TMDS]
  connect_bd_intf_net -intf_net images_m_axi_ddr [get_bd_intf_pins ddr/S00_AXI] [get_bd_intf_pins images/m_axi_ddr]
  connect_bd_intf_net -intf_net mixed_conv_m_axi_read_ddr [get_bd_intf_pins ddr/S04_AXI] [get_bd_intf_pins mixed_conv/m_axi_read_ddr]
  connect_bd_intf_net -intf_net mixed_conv_m_axi_write_ddr [get_bd_intf_pins ddr/S05_AXI] [get_bd_intf_pins mixed_conv/m_axi_write_ddr]
  connect_bd_intf_net -intf_net ps_M_AXI_HPM0_FPD [get_bd_intf_pins control/S00_AXI] [get_bd_intf_pins ps/M_AXI_HPM0_FPD]
  connect_bd_intf_net -intf_net video_dma_M_AXIS_MM2S [get_bd_intf_pins video_dma/M_AXIS_MM2S] [get_bd_intf_pins video_out/video_in]
  connect_bd_intf_net -intf_net video_dma_M_AXI_MM2S [get_bd_intf_pins ddr/S01_AXI] [get_bd_intf_pins video_dma/M_AXI_MM2S]
  connect_bd_intf_net -intf_net video_out_vid_io_out [get_bd_intf_pins hdmi_tx/Video_In] [get_bd_intf_pins video_out/vid_io_out]
  connect_bd_intf_net -intf_net video_timing_vtiming_out [get_bd_intf_pins video_out/vtiming_in] [get_bd_intf_pins video_timing/vtiming_out]

  # Create port connections
  connect_bd_net -net compute_clock_clk_out1 [get_bd_pins compute_clock/clk_out1] [get_bd_pins compute_reset/slowest_sync_clk] [get_bd_pins control/ACLK] [get_bd_pins control/M00_ACLK] [get_bd_pins control/M01_ACLK] [get_bd_pins control/M02_ACLK] [get_bd_pins control/M03_ACLK] [get_bd_pins control/M04_ACLK] [get_bd_pins control/S00_ACLK] [get_bd_pins ddr/ACLK] [get_bd_pins ddr/M00_ACLK] [get_bd_pins ddr/S00_ACLK] [get_bd_pins ddr/S01_ACLK] [get_bd_pins ddr/S02_ACLK] [get_bd_pins ddr/S03_ACLK] [get_bd_pins ddr/S04_ACLK] [get_bd_pins ddr/S05_ACLK] [get_bd_pins fast_deconv/ap_clk] [get_bd_pins images/ap_clk] [get_bd_pins mixed_conv/ap_clk] [get_bd_pins ps/maxihpm0_fpd_aclk] [get_bd_pins ps/saxihp2_fpd_aclk] [get_bd_pins video_dma/m_axi_mm2s_aclk] [get_bd_pins video_dma/m_axis_mm2s_aclk] [get_bd_pins video_dma/s_axi_lite_aclk] [get_bd_pins video_out/aclk] [get_bd_pins video_timing/s_axi_aclk]
  connect_bd_net -net compute_clock_locked [get_bd_pins compute_clock/locked] [get_bd_pins compute_reset/dcm_locked]
  connect_bd_net -net compute_reset_interconnect_aresetn [get_bd_pins compute_reset/interconnect_aresetn] [get_bd_pins control/ARESETN] [get_bd_pins ddr/ARESETN]
  connect_bd_net -net compute_reset_peripheral_aresetn [get_bd_pins compute_reset/peripheral_aresetn] [get_bd_pins control/M00_ARESETN] [get_bd_pins control/M01_ARESETN] [get_bd_pins control/M02_ARESETN] [get_bd_pins control/M03_ARESETN] [get_bd_pins control/M04_ARESETN] [get_bd_pins control/S00_ARESETN] [get_bd_pins ddr/M00_ARESETN] [get_bd_pins ddr/S00_ARESETN] [get_bd_pins ddr/S01_ARESETN] [get_bd_pins ddr/S02_ARESETN] [get_bd_pins ddr/S03_ARESETN] [get_bd_pins ddr/S04_ARESETN] [get_bd_pins ddr/S05_ARESETN] [get_bd_pins fast_deconv/ap_rst_n] [get_bd_pins images/ap_rst_n] [get_bd_pins mixed_conv/ap_rst_n] [get_bd_pins video_dma/axi_resetn] [get_bd_pins video_out/aresetn] [get_bd_pins video_timing/s_axi_aresetn]
  connect_bd_net -net hdmi_clocks_pixel_clk [get_bd_pins hdmi_clocks/pixel_clk] [get_bd_pins hdmi_tx/pclk] [get_bd_pins video_out/vid_io_out_clk] [get_bd_pins video_reset/slowest_sync_clk] [get_bd_pins video_timing/clk]
  connect_bd_net -net hdmi_clocks_serial_clk [get_bd_pins hdmi_clocks/serial_clk] [get_bd_pins hdmi_tx/pixel_clk_5x]
  connect_bd_net -net hdmi_clocks_serial_div_clk [get_bd_pins hdmi_clocks/serial_div_clk] [get_bd_pins hdmi_tx/pixel_clk_2_5x]
  connect_bd_net -net one_dout [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked] [get_bd_pins video_out/aclken] [get_bd_pins video_out/vid_io_out_ce] [get_bd_pins video_timing/clken] [get_bd_pins video_timing/s_axi_aclken]
  connect_bd_net -net pl_key1_n_1 [get_bd_ports pl_key1_n] [get_bd_pins pl_keys/key1_n]
  connect_bd_net -net pl_key2_n_1 [get_bd_ports pl_key2_n] [get_bd_pins pl_keys/key2_n]
  connect_bd_net -net pl_keys_emio_input [get_bd_pins pl_keys/emio_input] [get_bd_pins ps/emio_gpio_i]
  connect_bd_net -net ps_pl_clk0 [get_bd_pins compute_clock/clk_in1] [get_bd_pins pl_keys/clk] [get_bd_pins ps/pl_clk0] [get_bd_pins rst/slowest_sync_clk] [get_bd_pins video_mmcm/clk_in1]
  connect_bd_net -net ps_pl_resetn0 [get_bd_pins compute_reset/ext_reset_in] [get_bd_pins ps/pl_resetn0] [get_bd_pins rst/ext_reset_in] [get_bd_pins video_reset/ext_reset_in]
  connect_bd_net -net rst_interconnect_aresetn [get_bd_pins rst/interconnect_aresetn]
  connect_bd_net -net rst_peripheral_aresetn [get_bd_pins pl_keys/resetn] [get_bd_pins rst/peripheral_aresetn]
  connect_bd_net -net rst_peripheral_reset [get_bd_pins compute_clock/reset] [get_bd_pins rst/peripheral_reset] [get_bd_pins video_mmcm/reset]
  connect_bd_net -net video_mmcm_clk_out1 [get_bd_pins hdmi_clocks/clk_in] [get_bd_pins video_mmcm/clk_out1]
  connect_bd_net -net video_mmcm_locked [get_bd_pins hdmi_clocks/locked] [get_bd_pins video_mmcm/locked] [get_bd_pins video_reset/dcm_locked]
  connect_bd_net -net video_out_vtg_ce [get_bd_pins video_out/vtg_ce] [get_bd_pins video_timing/gen_clken]
  connect_bd_net -net video_reset_peripheral_aresetn [get_bd_pins hdmi_tx/reset_n] [get_bd_pins video_reset/peripheral_aresetn] [get_bd_pins video_timing/resetn]
  connect_bd_net -net video_reset_peripheral_reset [get_bd_pins video_out/vid_io_out_reset] [get_bd_pins video_reset/peripheral_reset]

  # Create address segments
  create_bd_addr_seg -range 0x80000000 -offset 0x00000000 [get_bd_addr_spaces fast_deconv/Data_m_axi_ddr] [get_bd_addr_segs ps/SAXIGP4/HP2_DDR_LOW] SEG_ps_HP2_DDR_LOW
  create_bd_addr_seg -range 0x80000000 -offset 0x00000000 [get_bd_addr_spaces fast_deconv/Data_m_axi_result_ddr] [get_bd_addr_segs ps/SAXIGP4/HP2_DDR_LOW] SEG_ps_HP2_DDR_LOW
  create_bd_addr_seg -range 0x80000000 -offset 0x00000000 [get_bd_addr_spaces images/Data_m_axi_ddr] [get_bd_addr_segs ps/SAXIGP4/HP2_DDR_LOW] SEG_ps_HP2_DDR_LOW
  create_bd_addr_seg -range 0x80000000 -offset 0x00000000 [get_bd_addr_spaces mixed_conv/Data_m_axi_read_ddr] [get_bd_addr_segs ps/SAXIGP4/HP2_DDR_LOW] SEG_ps_HP2_DDR_LOW
  create_bd_addr_seg -range 0x80000000 -offset 0x00000000 [get_bd_addr_spaces mixed_conv/Data_m_axi_write_ddr] [get_bd_addr_segs ps/SAXIGP4/HP2_DDR_LOW] SEG_ps_HP2_DDR_LOW
  create_bd_addr_seg -range 0x00010000 -offset 0xA1070000 [get_bd_addr_spaces ps/Data] [get_bd_addr_segs fast_deconv/s_axi_control/Reg] SEG_fast_deconv_Reg
  create_bd_addr_seg -range 0x00010000 -offset 0xA1020000 [get_bd_addr_spaces ps/Data] [get_bd_addr_segs images/s_axi_control/Reg] SEG_images_Reg
  create_bd_addr_seg -range 0x00010000 -offset 0xA1080000 [get_bd_addr_spaces ps/Data] [get_bd_addr_segs mixed_conv/s_axi_control/Reg] SEG_mixed_conv_Reg
  create_bd_addr_seg -range 0x00010000 -offset 0xA1050000 [get_bd_addr_spaces ps/Data] [get_bd_addr_segs video_dma/S_AXI_LITE/Reg] SEG_video_dma_Reg
  create_bd_addr_seg -range 0x00010000 -offset 0xA1060000 [get_bd_addr_spaces ps/Data] [get_bd_addr_segs video_timing/ctrl/Reg] SEG_video_timing_Reg
  create_bd_addr_seg -range 0x80000000 -offset 0x00000000 [get_bd_addr_spaces video_dma/Data_MM2S] [get_bd_addr_segs ps/SAXIGP4/HP2_DDR_LOW] SEG_ps_HP2_DDR_LOW


  # Restore current instance
  current_bd_instance $oldCurInst

  save_bd_design
}
# End of create_root_design()


##################################################################
# MAIN FLOW
##################################################################


common::send_msg_id "BD_TCL-2000" "CRITICAL WARNING" "This Tcl script was generated from a block design that is out-of-date/locked. It is possible that design <$design_name> may result in errors during construction."

create_root_design ""


