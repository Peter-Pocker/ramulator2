#include <vector>

#include "base/base.h"
#include "dram/dram.h"
#include "addr_mapper/addr_mapper.h"
#include "memory_system/memory_system.h"
#include <bitset>

namespace Ramulator {

class LinearMapperBase : public IAddrMapper {
  public:
    IDRAM* m_dram = nullptr;

    int m_num_levels = -1;          // How many levels in the hierarchy?
    std::vector<int> m_addr_bits;   // How many address bits for each level in the hierarchy?
    Addr_t m_tx_offset = -1;

    int m_col_bits_idx = -1;
    int m_row_bits_idx = -1;


  protected:
    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) {
      m_dram = memory_system->get_ifce<IDRAM>();

      // Populate m_addr_bits vector with the number of address bits for each level in the hierachy
      const auto& count = m_dram->m_organization.count;
      m_num_levels = count.size();
      m_addr_bits.resize(m_num_levels);
      for (size_t level = 0; level < m_addr_bits.size(); level++) {
        m_addr_bits[level] = calc_log2(count[level]);
      }

      // Last (Column) address have the granularity of the prefetch size
      m_addr_bits[m_num_levels - 1] -= calc_log2(m_dram->m_internal_prefetch_size);

      int tx_bytes = m_dram->m_internal_prefetch_size * m_dram->m_channel_width / 8;
      m_tx_offset = calc_log2(tx_bytes);

      // Determine where are the row and col bits for ChRaBaRoCo and RoBaRaCoCh
      try {
        m_row_bits_idx = m_dram->m_levels("row");
      } catch (const std::out_of_range& r) {
        throw std::runtime_error(fmt::format("Organization \"row\" not found in the spec, cannot use linear mapping!"));
      }

      // Assume column is always the last level
      m_col_bits_idx = m_num_levels - 1;
    }

};


class ChRaBaRoCo final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, ChRaBaRoCo, "ChRaBaRoCo", "Applies a trival mapping to the address.");

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);
      Addr_t addr = req.addr >> m_tx_offset;
      for (int i = m_addr_bits.size() - 1; i >= 0; i--) {
        req.addr_vec[i] = slice_lower_bits(addr, m_addr_bits[i]);
      }
    }
};


class RoBaRaCoCh final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, RoBaRaCoCh, "RoBaRaCoCh", "Applies a RoBaRaCoCh mapping to the address.");

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);
      Addr_t addr = req.addr >> m_tx_offset;
      req.addr_vec[0] = slice_lower_bits(addr, m_addr_bits[0]);
      req.addr_vec[m_addr_bits.size() - 1] = slice_lower_bits(addr, m_addr_bits[m_addr_bits.size() - 1]);
      for (int i = 1; i <= m_row_bits_idx; i++) {
        req.addr_vec[i] = slice_lower_bits(addr, m_addr_bits[i]);
      }
    }
};


class MOP4CLXOR final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, MOP4CLXOR, "MOP4CLXOR", "Applies a MOP4CLXOR mapping to the address.");

  public:
    void init() override { };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, -1);
      Addr_t addr = req.addr >> m_tx_offset;
      req.addr_vec[m_col_bits_idx] = slice_lower_bits(addr, 2);
      for (int lvl = 0 ; lvl < m_row_bits_idx ; lvl++)
          req.addr_vec[lvl] = slice_lower_bits(addr, m_addr_bits[lvl]);
      req.addr_vec[m_col_bits_idx] += slice_lower_bits(addr, m_addr_bits[m_col_bits_idx]-2) << 2;
      req.addr_vec[m_row_bits_idx] = (int) addr;

      int row_xor_index = 0; 
      for (int lvl = 0 ; lvl < m_col_bits_idx ; lvl++){
        if (m_addr_bits[lvl] > 0){
          int mask = (req.addr_vec[m_col_bits_idx] >> row_xor_index) & ((1<<m_addr_bits[lvl])-1);
          req.addr_vec[lvl] = req.addr_vec[lvl] xor mask;
          row_xor_index += m_addr_bits[lvl];
        }
      }
    }
};

class CustomizedMapper final : public LinearMapperBase, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IAddrMapper, CustomizedMapper, "CustomizedMapper", "Mapping the address with a customized method.");

  private:
  /* 
     C: column
     R: row
     B: bank
     BG: bankgroup
     RA: rank
     CH: channel
   */
    std::string mapping; // Mapping method. For example: "16R-2B-1G-7C-1G-3C".
    std::vector<int> addr_map; // Control every bit belongs to which level.
    int addr_bits;

  public:
    void init() override {
      mapping = param<std::string>("mapping").required();
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      LinearMapperBase::setup(frontend, memory_system);
      addr_bits = 0;
      for (int i : m_addr_bits) {
        addr_bits += i;
      }
      for (int i = 0; i < m_addr_bits.size(); ++i) {
        std::cout << "Bit length of " << m_dram->m_levels(i) << ": " << m_addr_bits[i] << std::endl;
      }

      addr_map.resize(addr_bits, -1);

      int num_bits = 0;
      int addr_idx_l = addr_bits-1, addr_idx_r = addr_idx_l;
      std::vector<int> bit_nums(m_addr_bits);

      for (int idx = 0; idx < mapping.size();) {
        switch (mapping[idx])
        {
        case 'C': /* column, channel */
          ++idx;
          if (idx == mapping.size() || mapping[idx] == '-') { /* column */
            bit_nums[m_dram->m_levels("column")] -= num_bits;
            for (addr_idx_r = addr_idx_l - num_bits; addr_idx_l > addr_idx_r; --addr_idx_l) {
              addr_map[addr_idx_l] = m_dram->m_levels("column");
            }
          } else if (mapping[idx] == 'H') { /* channel */
            bit_nums[m_dram->m_levels("channel")] -= num_bits;
            for (addr_idx_r = addr_idx_l - num_bits; addr_idx_l > addr_idx_r; --addr_idx_l) {
              addr_map[addr_idx_l] = m_dram->m_levels("channel");
            }
            ++idx; // Now `mapping[idx]` is '-'.
          }
          ++idx; // Skip the '-' or terminate the loop.
          num_bits = 0;
          break;

        case 'R': /* row, rank */
          ++idx;
          if (idx == mapping.size() || mapping[idx] == '-') { /* row */
            bit_nums[m_dram->m_levels("row")] -= num_bits;
            for (addr_idx_r = addr_idx_l - num_bits; addr_idx_l > addr_idx_r; --addr_idx_l) {
              addr_map[addr_idx_l] = m_dram->m_levels("row");
            }
          } else if (mapping[idx] == 'A') { /* rank */
            bit_nums[m_dram->m_levels("rank")] -= num_bits;
            for (addr_idx_r = addr_idx_l - num_bits; addr_idx_l > addr_idx_r; --addr_idx_l) {
              addr_map[addr_idx_l] = m_dram->m_levels("rank");
            }
            ++idx; // Now `mapping[idx]` is '-'.
          }
          ++idx; // Skip the '-' or terminate the loop.
          num_bits = 0;
          break;

        case 'B': /* bank, bankgroup */
          ++idx;
          // TODO: check whether the bit number is over 32. 
          if (idx == mapping.size() || mapping[idx] == '-') { /* bank */
            bit_nums[m_dram->m_levels("bank")] -= num_bits;
            for (addr_idx_r = addr_idx_l - num_bits; addr_idx_l > addr_idx_r; --addr_idx_l) {
              addr_map[addr_idx_l] = m_dram->m_levels("bank");
            }
          } else if (mapping[idx] == 'G') { /* bankgroup */
            bit_nums[m_dram->m_levels("bankgroup")] -= num_bits;
            for (addr_idx_r = addr_idx_l - num_bits; addr_idx_l > addr_idx_r; --addr_idx_l) {
              addr_map[addr_idx_l] = m_dram->m_levels("bankgroup");
            }
            ++idx; // Now `mapping[idx]` is '-'.
          }
          ++idx; // Skip the '-' or terminate the loop.
          num_bits = 0;
          break;

        default:
          int num = mapping[idx] - '0';
          if (num >= 0 && num <= 9) {
            num_bits = num + num_bits * 10;
          } else {
            throw std::runtime_error("Invalid character in mapping string.");
          }
          ++idx;
          break;
        }
      }
      for (int len : bit_nums) {
        if (len != 0) {
          throw std::runtime_error("Address bit length is not compatible with DRAM devices.");
        }
      }
    }

    void apply(Request& req) override {
      req.addr_vec.resize(m_num_levels, 0);
      Addr_t addr = req.addr >> m_tx_offset;
      for (int bit_idx = addr_bits-1; bit_idx >= 0; --bit_idx) {
        int level = addr_map[bit_idx];
        req.addr_vec[level] = (req.addr_vec[level] << 1) | ((addr >> bit_idx) & 1);
      }
#ifdef TREMBLE
      // Print detail info.
      std::bitset<28> addr_bit(addr);
      std::cout << "Addr: " << addr_bit << std::endl;
      for (int i = 0; i < m_addr_bits.size(); ++i) {
        std::bitset<28> bits(req.addr_vec[i]);
        std::string bit_str = bits.to_string();
        std::cout << m_dram->m_levels(i) << ": " << bit_str.substr(bit_str.size() - m_addr_bits[i]) << std::endl;
      }
#endif
    }
};

}   // namespace Ramulator