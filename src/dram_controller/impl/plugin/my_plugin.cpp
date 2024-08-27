#include <vector>
#include <unordered_map>
#include <limits>
#include <random>
#include <filesystem>
#include <fstream>

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/plugin.h"

namespace Ramulator {

class InfoRecorder : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, InfoRecorder, "InfoRecorder", "Collect information.")

  private:
    IDRAM* m_dram = nullptr;

    std::vector<std::vector<std::vector<std::vector<int>>>> m_rowhit_cnt;
    int m_rowhit_sum = 0;

    std::filesystem::path m_save_path; 


  public:
    void init() override { 
      m_save_path = param<std::string>("path").desc("Path to the output file").required();
      auto parent_path = m_save_path.parent_path();
      std::filesystem::create_directories(parent_path);
      if (!(std::filesystem::exists(parent_path) && std::filesystem::is_directory(parent_path))) {
        throw ConfigurationError("Invalid path to trace file: {}", parent_path.string());
      }
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      m_ctrl = cast_parent<IDRAMController>();
      m_dram = m_ctrl->m_dram;

      int channel_n = m_dram->m_organization.count[m_dram->m_levels("channel")];
      int rank_n = m_dram->m_organization.count[m_dram->m_levels("rank")];
      int bankgroup_n = (m_dram->m_organization.count.size() == 6) ? m_dram->m_organization.count[m_dram->m_levels("bankgroup")] : 1;
      int bank_n = m_dram->m_organization.count[m_dram->m_levels("bank")];

      m_rowhit_cnt.resize(channel_n);
      for (auto & chn : m_rowhit_cnt) {
        chn.resize(rank_n);
        for (auto & rank : chn) {
            rank.resize(bankgroup_n);
            for (auto & bg : rank) {
                bg.assign(bank_n, 0);
            }
        }
      }
    };

    void update(bool request_found, ReqBuffer::iterator& req_it) override {
      if (!request_found) {
        return;
      }
      if (!(req_it->command == m_dram->m_commands("RD") 
          || req_it->command == m_dram->m_commands("WR")
          || req_it->command == m_dram->m_commands("RDA")
          || req_it->command == m_dram->m_commands("WRA"))) {
        return;
      }
      if (m_dram->check_rowbuffer_hit(req_it->command, req_it->addr_vec)) {
        ++m_rowhit_sum;
        if (m_dram->m_organization.count.size() == 6) {
          ++(m_rowhit_cnt[req_it->addr_vec[m_dram->m_levels("channel")]]
                      [req_it->addr_vec[m_dram->m_levels("rank")]]
                      [req_it->addr_vec[m_dram->m_levels("bankgroup")]]
                      [req_it->addr_vec[m_dram->m_levels("bank")]]);
        } else {
          ++(m_rowhit_cnt[req_it->addr_vec[m_dram->m_levels("channel")]]
                      [req_it->addr_vec[m_dram->m_levels("rank")]]
                      [0]
                      [req_it->addr_vec[m_dram->m_levels("bank")]]);
        }
      }
    };

    void finalize() override {
      std::ofstream output(m_save_path);
      output << fmt::format("Total row hit count: {}", m_rowhit_sum) << std::endl;
      if (m_dram->m_organization.count.size() == 6) {
        output << "channel, rank, bankgroup, bank: row hit" << std::endl;
      } else {
        output << "channel, rank, bank: row hit" << std::endl;
      }
      
      int ch_id = 0, rk_id, bg_id, bn_id;
      for (auto ch : m_rowhit_cnt) {
        rk_id = 0;
        for (auto rk : ch) {
          bg_id = 0;
          for (auto bg : rk) {
            bn_id = 0;
            for (auto bn : bg) {
              if (m_dram->m_organization.count.size() == 6) {
                output << fmt::format("{:2}, {:2}, {:2}, {:2}: {:6}", ch_id, rk_id, bg_id, bn_id, bn) << std::endl;
              } else {
                output << fmt::format("{:2}, {:2}, {:2}: {:6}", ch_id, rk_id, bn_id, bn) << std::endl;
              }
              ++bn_id;
            }
            ++bg_id;
          }
          ++rk_id;
        }
        ++ch_id;
      }
      output.close();
    }

};

}       // namespace Ramulator
